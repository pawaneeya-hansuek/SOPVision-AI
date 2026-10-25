"""Test runs, auditable supervisor decisions and stale inspection handling."""
from __future__ import annotations
import hashlib
import json
import secrets
import threading
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import db
import auth

router=APIRouter(tags=['Work management'])
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')

def initialize_schema(c):
    for table,name,definition in [
        ('flow_jobs','is_test','INTEGER NOT NULL DEFAULT 0'),
        ('flow_jobs','source_qr','TEXT'),
        ('flow_jobs','test_run_id','TEXT'),
        ('flow_attempts','last_frame_at','TEXT'),
        ('flow_attempts','rework_of','TEXT'),
        ('camera_sessions','owner_id','INTEGER')]:
        if name not in {r['name'] for r in c.execute('PRAGMA table_info('+table+')')}:
            c.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
    c.execute("""CREATE TABLE IF NOT EXISTS test_runs(
      id TEXT PRIMARY KEY,label TEXT NOT NULL,created_by INTEGER REFERENCES users(id),created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS supervisor_reviews(
      attempt_id TEXT PRIMARY KEY REFERENCES flow_attempts(id),status TEXT NOT NULL DEFAULT 'pending',
      decision TEXT,reason TEXT,reviewer_id INTEGER REFERENCES users(id),
      created_at TEXT NOT NULL,reviewed_at TEXT)""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS queue_failed_attempt
      AFTER UPDATE OF ended_at ON flow_attempts WHEN NEW.ended_at IS NOT NULL
      AND NEW.state IN ('blocked','interrupted')
      BEGIN INSERT OR IGNORE INTO supervisor_reviews(attempt_id,created_at)
      VALUES(NEW.id,NEW.ended_at); END""")
    c.execute("""INSERT OR IGNORE INTO supervisor_reviews(attempt_id,created_at)
      SELECT id,ended_at FROM flow_attempts WHERE ended_at IS NOT NULL AND state IN ('blocked','interrupted')""")

class NewRun(BaseModel):
    label:str=Field(default='รอบทดสอบ',min_length=1,max_length=80)
@router.get('/api/test-runs')
def test_runs():
    with db.connect() as c:return [dict(r) for r in c.execute('SELECT id,label,created_at FROM test_runs ORDER BY created_at DESC,rowid DESC LIMIT 30')]
@router.post('/api/test-runs')
def new_run(body:NewRun):
    actor=auth.user();key=secrets.token_hex(12)
    with db.connect() as c:
        c.execute('INSERT INTO test_runs VALUES(?,?,?,?)',(key,body.label,actor['id'] if actor and not actor.get('guest') else None,now()))
        auth.audit(c,'test_run_created',key,body.label)
    return {'id':key,'label':body.label}

def job_key(qr,test_mode=False,test_run_id=None):
    if qr.startswith('__TEST__:'):
        raise HTTPException(400,'รหัสขึ้นต้น __TEST__: สงวนให้ระบบ')
    if not test_mode:return qr
    if not test_run_id:raise HTTPException(400,'เลือกรอบทดสอบก่อนเริ่มงาน')
    with db.connect() as c:
        if not c.execute('SELECT 1 FROM test_runs WHERE id=?',(test_run_id,)).fetchone():raise HTTPException(404,'ไม่พบรอบทดสอบ')
    return '__TEST__:'+test_run_id+':'+hashlib.sha256(qr.encode()).hexdigest()[:24]

def approved_attempts(c,qr):
    return {r['attempt_id'] for r in c.execute("""SELECT r.attempt_id FROM supervisor_reviews r
       JOIN flow_attempts a ON a.id=r.attempt_id WHERE a.qr=? AND r.decision='rework_approved'""",(qr,))}

def staff():
    actor=auth.user()
    if not actor or actor['role'] not in ('admin','supervisor','qc'):
        raise HTTPException(403,'เฉพาะผู้ตรวจคุณภาพ หัวหน้างาน หรือแอดมิน')
    return actor

@router.get('/access')
def access_page():
    from fastapi.responses import FileResponse
    return FileResponse(auth.ROOT/'static/access.html')

@router.get('/api/reviews')
def reviews(scope:str='production',status:str='pending'):
    staff()
    if scope not in ('production','test','all') or status not in ('pending','closed','all'):
        raise HTTPException(400,'ตัวกรองไม่ถูกต้อง')
    clauses=[];params=[]
    if scope!='all':clauses.append('j.is_test=?');params.append(int(scope=='test'))
    if status!='all':clauses.append('r.status=?');params.append(status)
    with db.connect() as c:
        rows=c.execute("""SELECT r.*,a.qr,a.station_id,a.operator,a.state,a.result_json,
          a.started_at,a.video_url,a.frame_url,j.is_test,j.source_qr,
          u.display_name reviewer_name FROM supervisor_reviews r
          JOIN flow_attempts a ON a.id=r.attempt_id JOIN flow_jobs j ON j.qr=a.qr
          LEFT JOIN users u ON u.id=r.reviewer_id"""+
          (' WHERE '+' AND '.join(clauses) if clauses else '')+
          ' ORDER BY r.created_at DESC,r.rowid DESC LIMIT 200',params).fetchall()
    result=[]
    for row in rows:
        d=dict(row);d['result']=json.loads(d.pop('result_json') or '{}');result.append(d)
    return result

class Decision(BaseModel):
    decision:str
    reason:str=Field(min_length=10,max_length=2000)
@router.post('/api/reviews/{attempt_id}/decision')
def decide(attempt_id:str,body:Decision):
    actor=staff()
    if len(body.reason.strip())<10:raise HTTPException(400,'กรุณาระบุเหตุผลอย่างน้อย 10 ตัวอักษร')
    if body.decision not in ('rework_approved','rejected'):raise HTTPException(400,'ผลตัดสินไม่ถูกต้อง')
    if actor['role']=='supervisor' and body.decision!='rework_approved':
        raise HTTPException(403,'หัวหน้างานอนุญาตสแกนงานซ้ำได้เท่านั้น')
    if body.decision=='rework_approved' and actor['role'] not in ('admin','supervisor'):
        raise HTTPException(403,'เฉพาะหัวหน้าหรือแอดมินอนุญาตให้ตรวจซ้ำได้')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        review=c.execute('SELECT * FROM supervisor_reviews WHERE attempt_id=?',(attempt_id,)).fetchone()
        attempt=c.execute('SELECT * FROM flow_attempts WHERE id=?',(attempt_id,)).fetchone()
        if not review or not attempt:raise HTTPException(404,'ไม่พบงานที่รอตรวจ')
        if not attempt['ended_at']:raise HTTPException(409,'รอปิดงานเดิมก่อนตัดสิน')
        if review['status']!='pending':raise HTTPException(409,'รายการนี้มีผลตัดสินแล้ว โหลดข้อมูลใหม่')
        c.execute("""UPDATE supervisor_reviews SET status='closed',decision=?,reason=?,reviewer_id=?,reviewed_at=?
          WHERE attempt_id=? AND status='pending'""",(body.decision,body.reason.strip(),actor['id'],now(),attempt_id))
        c.execute('INSERT INTO flow_audit(attempt_id,qr,event,event_at,detail) VALUES(?,?,?,?,?)',
                  (attempt_id,attempt['qr'],body.decision,now(),actor['username']+': '+body.reason.strip()))
        auth.audit(c,body.decision,attempt_id,body.reason.strip())
    return {'ok':True,'decision':body.decision,'note':'เก็บผลตรวจเดิมไว้ ไม่มีการเปลี่ยนผลเดิมให้ผ่าน'}

@router.get('/api/security-audit')
def security_audit():
    actor=staff()
    if actor['role']!='admin':raise HTTPException(403,'เฉพาะผู้ดูแลระบบ')
    with db.connect() as c:return [dict(r) for r in c.execute("""SELECT a.id,a.event,a.target,a.detail,a.happened_at,
      u.username actor FROM security_audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 200""")]

@router.get('/api/flow/my-history')
def my_history(station_id:int=Query(ge=1,le=3),scope:str='production'):
    from reporting import snapshot
    actor=auth.user()
    if not actor:raise HTTPException(401,'กรุณาเข้าสู่ระบบ')
    from station_access import operator_for
    data=snapshot(operator=operator_for(actor,station_id),station_id=station_id,limit=15,scope=scope)
    data['stats']=data['filtered_stats']
    return data

def expire_stale(seconds=45):
    """No camera inspection frames for 45s: retain evidence and close without passing."""
    import production
    cutoff=(datetime.now(timezone.utc)-timedelta(seconds=seconds)).isoformat(timespec='seconds')
    closed=[]
    with production.lock,db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=c.execute("""SELECT * FROM flow_attempts WHERE ended_at IS NULL
          AND julianday(coalesce(last_frame_at,started_at))<julianday(?)""",(cutoff,)).fetchall()
        for r in rows:
            result=json.loads(r['result_json'] or '{}')
            result['status']='review';result['issues']=max(1,result.get('issues',0))
            result['error']='ไม่ได้รับภาพตรวจงานเกิน 45 วินาที งานถูกแยกพักและไม่ปลดล็อก'
            for step in result.get('steps',[]):
                if step.get('status')!='passed':step['status']='missing'
            state='blocked' if r['state']=='blocked' else 'interrupted'
            ended=now()
            c.execute("""UPDATE flow_attempts SET state=?,ended_at=?,updated_at=?,result_json=?
              WHERE id=? AND ended_at IS NULL""",(state,ended,ended,json.dumps(result,ensure_ascii=False),r['id']))
            c.execute('INSERT INTO flow_audit(attempt_id,qr,event,event_at,detail) VALUES(?,?,?,?,?)',
                      (r['id'],r['qr'],'connection_timeout',ended,result['error']))
            c.execute('UPDATE camera_work_links SET unlinked_at=? WHERE attempt_id=? AND unlinked_at IS NULL',(ended,r['id']))
            closed.append(r['id'])
        for sid in closed:production.active.pop(sid,None)
        # A missing video upload must never reopen a completed inspection.
        archive_cutoff=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat(timespec='seconds')
        pending=c.execute("""SELECT id,result_json FROM flow_attempts WHERE state='passed'
          AND json_extract(result_json,'$.recording_pending')=1
          AND julianday(updated_at)<julianday(?)""",(archive_cutoff,)).fetchall()
        for row in pending:
            result=json.loads(row['result_json'])
            result['recording_pending']=False
            result['recording_error']='ส่งวิดีโอไม่ครบภายในเวลาที่กำหนด ผลตรวจที่ผ่านแล้วคงเดิม'
            c.execute('UPDATE flow_attempts SET result_json=?,updated_at=? WHERE id=?',
                      (json.dumps(result,ensure_ascii=False),now(),row['id']))
            production.active.pop(row['id'],None)
    return closed

def install(app):
    app.include_router(router)


async def start_watchdog(app):
    import asyncio
    from fastapi.concurrency import run_in_threadpool
    async def loop():
        while True:
            await asyncio.sleep(5)
            try:
                await run_in_threadpool(expire_stale)
                import cameras
                await run_in_threadpool(cameras.expire_stale)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Inspection watchdog failed')
    app.state.inspection_watchdog=asyncio.create_task(loop())


async def stop_watchdog(app):
    import asyncio
    from contextlib import suppress
    task=getattr(app.state,'inspection_watchdog',None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
