"""Camera sharing independent of workpiece inspection. One production backend."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from fastapi import APIRouter, File, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import db

router = APIRouter(prefix='/api/cameras', tags=['Camera monitoring'])
MEDIA = Path(__file__).resolve().parent / 'media' / 'cameras'
MEDIA.mkdir(parents=True, exist_ok=True)
lock = threading.RLock()
latest: dict[str, tuple[int, bytes]] = {}
MAX_CHUNK = 8 * 1024 * 1024
MAX_SEGMENT = 32 * 1024 * 1024
ID_PATTERN = r'^[a-zA-Z0-9_-]{16,80}$'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def age(timestamp):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace('Z', '+00:00'))).total_seconds()


def authenticate(c, cid, token, require_open=True):
    row = c.execute('SELECT * FROM camera_sessions WHERE id=?', (cid,)).fetchone()
    if row is None:
        raise HTTPException(404, 'ไม่พบกล้อง')
    digest = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(row['token_hash'], digest):
        raise HTTPException(403, 'สิทธิ์ส่งภาพกล้องไม่ถูกต้อง')
    if require_open and row['state'] != 'open':
        raise HTTPException(409, 'กล้องนี้ปิดแล้ว กรุณาเปิดกล้องใหม่')
    return row


def segment_file(cid, index, mime):
    return MEDIA / f'{cid}_{index}{".mp4" if mime.startswith("video/mp4") else ".webm"}'


class Open(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    token: str = Field(min_length=32, max_length=128)
    source: Literal['worker', 'flow', 'live', 'qr']
    station_id: int | None = Field(default=None, ge=1, le=3)
    operator: str = Field(default='', max_length=80)
    device_label: str = Field(default='กล้อง', max_length=200)
    mime_type: str = Field(max_length=80)


@router.post('/open')
def open_camera(body: Open):
    import auth
    actor=auth.user()
    if actor and actor['role']!='admin':
        from station_access import operator_for
        body=body.model_copy(update={'operator':operator_for(actor,body.station_id)})
    if not (body.mime_type.startswith('video/webm') or body.mime_type.startswith('video/mp4')):
        raise HTTPException(400, 'รูปแบบวิดีโอไม่รองรับ')
    with lock, db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        existing = c.execute('SELECT * FROM camera_sessions WHERE id=?', (body.id,)).fetchone()
        if existing:
            row = authenticate(c, body.id, body.token)
            if (row['source'], row['station_id'], row['operator'], row['mime_type']) != (body.source, body.station_id, body.operator.strip(), body.mime_type):
                raise HTTPException(409, 'รหัสกล้องเดิมมีข้อมูลไม่ตรงกัน')
        else:
            c.execute('''INSERT INTO camera_sessions(id,token_hash,source,station_id,operator,device_label,
                         mime_type,started_at,last_seen,state) VALUES(?,?,?,?,?,?,?,?,?,'open')''',
                      (body.id, hashlib.sha256(body.token.encode()).hexdigest(), body.source, body.station_id,
                       body.operator.strip(), body.device_label, body.mime_type, now(), now()))
        if actor:
            c.execute('UPDATE camera_sessions SET owner_id=? WHERE id=?',(actor['id'],body.id))
    return {'id': body.id, 'segment_ms': 30000, 'preview_ms': 250}


@router.post('/{cid}/frame/{sequence}')
async def preview(cid: str, sequence: int, frame: UploadFile = File(...), x_camera_key: str = Header(default='')):
    data = await frame.read(1_000_001)
    return await run_in_threadpool(store_preview, cid, sequence, data, x_camera_key)


def store_preview(cid, sequence, data, x_camera_key):
    if sequence < 0 or not data or len(data) > 1_000_000:
        raise HTTPException(400, 'ข้อมูลภาพไม่ถูกต้อง')
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, 'อ่านภาพกล้องไม่ได้')
    ok, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not ok:
        raise HTTPException(400, 'แปลงภาพกล้องไม่ได้')
    digest = hashlib.sha256(data).hexdigest()
    with lock, db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = authenticate(c, cid, x_camera_key)
        if sequence <= row['frame_sequence']:
            if sequence == row['frame_sequence'] and row['frame_hash'] == digest:
                return {'sequence': sequence, 'duplicate': True}
            raise HTTPException(409, 'ลำดับภาพเก่าหรือข้อมูลซ้ำไม่ตรงกัน')
        c.execute('UPDATE camera_sessions SET frame_sequence=?,frame_hash=?,frame_at=?,last_seen=? WHERE id=?',
                  (sequence, digest, now(), now(), cid))
        c.commit()
        latest[cid] = (sequence, jpg.tobytes())
    return {'sequence': sequence}


@router.get('/{cid}/live')
async def live(cid: str):
    with db.connect() as c:
        row = c.execute('SELECT state FROM camera_sessions WHERE id=?', (cid,)).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบกล้อง')
    if row['state'] != 'open' or cid not in latest:
        raise HTTPException(409, 'กล้องยังไม่มีภาพสดหรือหยุดส่งภาพแล้ว')
    async def frames():
        previous = -1
        idle = 0
        deadline = time.monotonic() + 20
        while idle < 150 and time.monotonic() < deadline:
            item = latest.get(cid)
            if not item:
                return
            if item[0] != previous:
                previous = item[0]; idle = 0
                yield b'--camera\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(item[1])).encode() + b'\r\n\r\n' + item[1] + b'\r\n'
            else:
                idle += 1
            await asyncio.sleep(.1)
    return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=camera',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@router.post('/{cid}/segments/{index}/chunks/{sequence}')
async def chunk(cid: str, index: int, sequence: int, chunk: UploadFile = File(...), x_camera_key: str = Header(default='')):
    payload = await chunk.read(MAX_CHUNK + 1)
    return await run_in_threadpool(store_chunk, cid, index, sequence, payload, x_camera_key)


def store_chunk(cid, index, sequence, payload, x_camera_key):
    if index < 0 or sequence < 0 or not payload or len(payload) > MAX_CHUNK:
        raise HTTPException(400, 'ชิ้นส่วนวิดีโอไม่ถูกต้อง')
    digest = hashlib.sha256(payload).hexdigest()
    with lock, db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = authenticate(c, cid, x_camera_key)
        segment = c.execute('SELECT * FROM camera_segments WHERE camera_id=? AND segment_index=?', (cid,index)).fetchone()
        if segment:
            existing = c.execute('SELECT digest FROM camera_chunks WHERE camera_id=? AND segment_index=? AND sequence=?', (cid,index,sequence)).fetchone()
            if existing:
                if existing['digest'] != digest:
                    raise HTTPException(409, 'วิดีโอลำดับเดิมมีข้อมูลไม่ตรงกัน')
                return {'duplicate': True, 'chunks': segment['chunks'], 'bytes': segment['bytes']}
            if segment['state'] != 'recording' or sequence != segment['chunks']:
                raise HTTPException(409, 'ลำดับวิดีโอไม่ตรงกันหรือคลิปปิดแล้ว')
        else:
            if sequence != 0:
                raise HTTPException(409, 'คลิปต้องเริ่มจากส่วนแรก')
            c.execute("INSERT INTO camera_segments(camera_id,segment_index,started_at,state) VALUES(?,?,?,'recording')", (cid,index,now()))
        size = segment['bytes'] if segment else 0
        if size + len(payload) > MAX_SEGMENT or shutil.disk_usage(MEDIA).free < len(payload) + 100*1024*1024:
            raise HTTPException(507, 'พื้นที่บันทึกวิดีโอไม่พอหรือคลิปใหญ่เกินกำหนด')
        file = segment_file(cid,index,row['mime_type'])
        if (file.stat().st_size if file.exists() else 0) != size:
            raise HTTPException(409, 'ขนาดไฟล์คลิปไม่ตรงกับข้อมูลที่รับ')
        try:
            with file.open('ab') as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
            c.execute('INSERT INTO camera_chunks VALUES(?,?,?,?,?)', (cid,index,sequence,digest,len(payload)))
            c.execute('UPDATE camera_segments SET chunks=chunks+1,bytes=bytes+? WHERE camera_id=? AND segment_index=?', (len(payload),cid,index))
            c.execute('UPDATE camera_sessions SET last_seen=? WHERE id=?', (now(),cid))
            c.commit()
        except BaseException:
            if file.exists():
                with file.open('r+b') as f:
                    f.truncate(size)
            raise
    return {'chunks': sequence+1, 'bytes': size+len(payload)}


class Finish(BaseModel):
    chunks: int = Field(ge=1)
    bytes: int = Field(ge=1)


@router.post('/{cid}/segments/{index}/finish')
def finish_segment(cid: str, index: int, body: Finish, x_camera_key: str = Header(default='')):
    with lock, db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        session = authenticate(c,cid,x_camera_key,require_open=False)
        segment = c.execute('SELECT * FROM camera_segments WHERE camera_id=? AND segment_index=?',(cid,index)).fetchone()
        if not segment:
            raise HTTPException(404, 'ไม่พบคลิป')
        file = segment_file(cid,index,session['mime_type'])
        if (segment['chunks'],segment['bytes']) != (body.chunks,body.bytes) or not file.exists() or file.stat().st_size != body.bytes:
            raise HTTPException(409, 'ยังรับคลิปไม่ครบ ไม่สามารถยืนยันการบันทึกได้')
        if segment['state'] == 'partial':
            raise HTTPException(409, 'คลิปหยุดกลางคันแล้ว')
        c.execute("UPDATE camera_segments SET state='complete',ended_at=coalesce(ended_at,?) WHERE camera_id=? AND segment_index=?", (now(),cid,index))
    return {'state':'complete'}


class Close(BaseModel):
    token: str = Field(max_length=128)
    error: str = Field(default='', max_length=300)


class WorkLink(BaseModel):
    qr: str | None = Field(default=None, min_length=1, max_length=200)
    attempt_id: str = Field(min_length=1, max_length=80)


@router.post('/{cid}/work-link')
def link_work(cid: str, body: WorkLink, x_camera_key: str = Header(default='')):
    with lock, db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        authenticate(c, cid, x_camera_key)
        link = c.execute('''SELECT * FROM camera_work_links
                            WHERE camera_id=? AND attempt_id=?''',
                         (cid, body.attempt_id)).fetchone()
        if body.qr is None:
            if link is None:
                raise HTTPException(404, 'ไม่พบการเชื่อมกล้องกับรอบงาน')
            if link['unlinked_at'] is None:
                c.execute('''UPDATE camera_work_links SET unlinked_at=?
                             WHERE camera_id=? AND attempt_id=?''',
                          (now(), cid, body.attempt_id))
            return {'linked': False, 'attempt_id': body.attempt_id}
        attempt = c.execute('SELECT qr,state,ended_at FROM flow_attempts WHERE id=?',
                            (body.attempt_id,)).fetchone()
        if attempt is None or attempt['qr'] != body.qr:
            raise HTTPException(400, 'รอบงานไม่ตรงกับ QR ที่ระบุ')
        if attempt['state'] != 'active' or attempt['ended_at'] is not None:
            raise HTTPException(409, 'เชื่อมกล้องได้เฉพาะรอบงานที่กำลังทำอยู่')
        if link and link['unlinked_at'] is None:
            if link['qr'] != body.qr:
                raise HTTPException(409, 'รอบงานนี้ถูกเชื่อมกับ QR อื่นไว้แล้ว')
            return {'linked': True, 'qr': body.qr, 'attempt_id': body.attempt_id}
        c.execute('UPDATE camera_work_links SET unlinked_at=? WHERE camera_id=? AND unlinked_at IS NULL',
                  (now(), cid))
        c.execute('''INSERT INTO camera_work_links(camera_id,qr,attempt_id,linked_at,unlinked_at)
                     VALUES(?,?,?,?,NULL)
                     ON CONFLICT(camera_id,attempt_id) DO UPDATE SET
                     qr=excluded.qr,linked_at=excluded.linked_at,unlinked_at=NULL''',
                  (cid, body.qr, body.attempt_id, now()))
    return {'linked': True, 'qr': body.qr, 'attempt_id': body.attempt_id}


@router.post('/{cid}/close')
def close_camera(cid: str, body: Close):
    with lock, db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = authenticate(c,cid,body.token,require_open=False)
        state = row['state']
        if row['state'] == 'open':
            state = 'interrupted' if body.error else 'closed'
            c.execute("UPDATE camera_sessions SET state=?,ended_at=?,error=? WHERE id=?", (state,now(),body.error or None,cid))
            c.execute("UPDATE camera_segments SET state='partial',ended_at=? WHERE camera_id=? AND state='recording'", (now(),cid))
            c.execute('UPDATE camera_work_links SET unlinked_at=? WHERE camera_id=? AND unlinked_at IS NULL',
                      (now(), cid))
        latest.pop(cid,None)
    return {'state':state}


def camera_display(row):
    d = dict(row); d.pop('token_hash',None); d.pop('frame_hash',None)
    d['online'] = d['state']=='open' and bool(d['frame_at']) and age(d['frame_at']) <= 5
    d['live_url'] = f'/api/cameras/{d["id"]}/live'
    return d


@router.get('/events')
async def events():
    def snapshot():
        with lock:
            return dict(latest)

    async def stream():
        versions = {}
        heartbeat = time.monotonic()
        deadline = heartbeat + 20
        yield 'retry: 500\n\n'
        # Bounded streams allow a development server reload to drain cleanly.
        # EventSource automatically reconnects and receives the latest frames.
        while time.monotonic() < deadline:
            current = await run_in_threadpool(snapshot)
            changed = [{'id':cid, 'sequence':value[0], 'jpeg':base64.b64encode(value[1]).decode('ascii')}
                       for cid,value in current.items() if versions.get(cid) != value[0]]
            versions = {cid:value[0] for cid,value in current.items()}
            if changed:
                yield 'data: ' + json.dumps({'frames':changed}) + '\n\n'
                heartbeat = time.monotonic()
            elif time.monotonic()-heartbeat >= 10:
                yield ': heartbeat\n\n'
                heartbeat = time.monotonic()
            await asyncio.sleep(.2)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


def expire_stale():
    with lock, db.connect() as c:
        # A frozen mobile tab is offline; never present its last frame as live.
        cutoff = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()-45,timezone.utc).isoformat()
        if not c.execute("SELECT 1 FROM camera_sessions WHERE state='open' AND last_seen<? LIMIT 1", (cutoff,)).fetchone():
            return []
        c.execute('BEGIN IMMEDIATE')
        stale = [r['id'] for r in c.execute("SELECT id FROM camera_sessions WHERE state='open' AND last_seen<?",(cutoff,))]
        for cid in stale:
            c.execute("UPDATE camera_sessions SET state='interrupted',ended_at=?,error='ขาดการเชื่อมต่อเกิน 45 วินาที' WHERE id=?",(now(),cid))
            c.execute("UPDATE camera_segments SET state='partial',ended_at=? WHERE camera_id=? AND state='recording'",(now(),cid))
            c.execute('UPDATE camera_work_links SET unlinked_at=? WHERE camera_id=? AND unlinked_at IS NULL',
                      (now(), cid))
            latest.pop(cid,None)
    return stale


@router.get('')
def list_cameras(response: Response):
    response.headers['Cache-Control']='no-store'
    expire_stale()
    with db.connect() as c:
        rows = c.execute("""SELECT s.*,(SELECT l.qr FROM camera_work_links l
                             WHERE l.camera_id=s.id AND l.unlinked_at IS NULL
                             ORDER BY l.linked_at DESC LIMIT 1) linked_qr
                             FROM camera_sessions s WHERE s.state='open'
                             ORDER BY s.started_at DESC""").fetchall()
    return {'cameras':[camera_display(r) for r in rows], 'generated_at':now()}


@router.get('/archive')
def archive(response: Response, q: str = Query(default='',max_length=300), station_id: int | None = Query(default=None,ge=1,le=3),
            source: Literal['all','worker','flow','live','qr']='all',
            since: datetime | None = None, until: datetime | None = None,
            offset: int = Query(default=0,ge=0), limit: int = Query(default=30,ge=1,le=100)):
    response.headers['Cache-Control']='no-store'
    where, args = [], []
    if q.strip():
        value=q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        where.append("""(s.operator LIKE ? ESCAPE '\\' OR s.device_label LIKE ? ESCAPE '\\'
                         OR s.id LIKE ? ESCAPE '\\' OR EXISTS(
                         SELECT 1 FROM camera_work_links l WHERE l.camera_id=s.id
                         AND l.qr LIKE ? ESCAPE '\\'
                         AND l.linked_at<=coalesce(v.ended_at,?)
                         AND (l.unlinked_at IS NULL OR l.unlinked_at>=v.started_at)))""")
        args.extend(['%'+value+'%']*4+[now()])
    if station_id is not None:
        where.append('s.station_id=?');args.append(station_id)
    if source!='all':
        where.append('s.source=?');args.append(source)
    for value,op in [(since,'>='),(until,'<=')]:
        if value:
            if value.tzinfo is None:
                raise HTTPException(400,'เวลาค้นหาต้องมีเขตเวลา')
            where.append('v.started_at'+op+'?');args.append(value.astimezone(timezone.utc).isoformat(timespec='milliseconds'))
    if since and until and since > until:
        raise HTTPException(400,'เวลาเริ่มต้องไม่เกินเวลาสิ้นสุด')
    clause=' WHERE '+' AND '.join(where) if where else ''
    query=' FROM camera_segments v JOIN camera_sessions s ON s.id=v.camera_id'
    with db.connect() as c:
        c.execute('BEGIN')
        total=c.execute('SELECT count(*)'+query+clause,args).fetchone()[0]
        rows=c.execute('''SELECT v.*,s.source,s.station_id,s.operator,s.device_label,s.mime_type,s.state camera_state,s.error,
                         (SELECT group_concat(l.qr, ', ') FROM camera_work_links l
                          WHERE l.camera_id=s.id AND l.linked_at<=coalesce(v.ended_at,?)
                          AND (l.unlinked_at IS NULL OR l.unlinked_at>=v.started_at)) related_qrs'''
                       +query+clause+' ORDER BY v.started_at DESC,v.camera_id, v.segment_index DESC LIMIT ? OFFSET ?',
                       [now(),*args,limit,offset]).fetchall()
    items=[]
    for row in rows:
        d=dict(row);file=segment_file(d['camera_id'],d['segment_index'],d['mime_type'])
        d['available']=d['state']!='recording' and d['bytes']>0 and file.is_file()
        d['video_url']=f'/api/cameras/{d["camera_id"]}/segments/{d["segment_index"]}/video' if d['available'] else None
        items.append(d)
    return {'segments':items,'total':total,'offset':offset,'limit':limit}


@router.get('/{cid}/segments/{index}/video')
def recording(cid: str,index: int):
    with db.connect() as c:
        row=c.execute('''SELECT v.*,s.mime_type FROM camera_segments v JOIN camera_sessions s ON s.id=v.camera_id
                         WHERE camera_id=? AND segment_index=?''',(cid,index)).fetchone()
    if not row:
        raise HTTPException(404,'ไม่พบคลิป')
    if row['state']=='recording':
        raise HTTPException(409,'คลิปกำลังบันทึก กรุณารอปิดคลิป')
    file=segment_file(cid,index,row['mime_type'])
    if not file.is_file() or not row['bytes']:
        raise HTTPException(404,'ไม่พบไฟล์วิดีโอ')
    from playback import video_response
    return video_response(file)
