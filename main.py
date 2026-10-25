"""SOPVision AI: live webcam and uploaded-video assembly step inspector.
Run: uvicorn main:app --reload  (from project directory)
"""
from __future__ import annotations
import os
import io
import uuid
import time
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from playback import RecordedMedia
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import db
from gemini_review import review_images
from production import router as production_router, station_for
from cameras import router as camera_router
from vision import HSV, Tracker, detect_colors, annotated, jpeg, LIVE_SAMPLE_MS, VIDEO_SAMPLE_FPS

ROOT = Path(__file__).resolve().parent

def inspection_build():
    digest = hashlib.sha256()
    for name in ('main.py', 'production.py', 'vision.py', 'static/worker.js'):
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()[:16]

INSPECTION_BUILD = inspection_build()
MEDIA = ROOT/'media'
EVIDENCE = MEDIA/'evidence'
UPLOADS = MEDIA/'uploads'
for d in (MEDIA,EVIDENCE,UPLOADS): d.mkdir(parents=True,exist_ok=True)

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

@asynccontextmanager
async def lifespan(app):
    from runtime_guard import BackendGuard
    with BackendGuard(db.DB):
        await run_in_threadpool(db.initialize)
        await workflows.start_watchdog(app)
        try:
            yield
        finally:
            await workflows.stop_watchdog(app)


app = FastAPI(title='SOPVision AI', description='Hybrid video/live inspection prototype', lifespan=lifespan)
app.include_router(production_router)
from reporting import router as reporting_router
app.include_router(reporting_router)
from supervisor import router as supervisor_router
app.include_router(supervisor_router)
import auth,workflows
auth.install(app)
workflows.install(app)
app.include_router(camera_router)
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
app.mount('/media', RecordedMedia(directory=MEDIA), name='media')

@app.get('/')
def index(): return FileResponse(ROOT/'static'/'index.html')

@app.get('/worker')
def worker_page(): return FileResponse(ROOT/'static'/'worker.html')

@app.get('/admin')
def admin_page(): return FileResponse(ROOT/'static'/'admin.html')

@app.post('/api/qr/decode')
async def decode_qr(frame: UploadFile=File(...)):
    image = decoded_image(await frame.read(3_000_001))
    def scan():
        value, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
        return {'qr': value or None}
    return await run_in_threadpool(scan)

@app.get('/api/health')
def health():
    return {'ok': True, 'mode':'color-marker computer vision',
            'frame_protocol': 2, 'inspection_engine': 'color-count-2',
            'instant_completion': True,
            'inspection_build': INSPECTION_BUILD,
            'needs_restart': inspection_build() != INSPECTION_BUILD,
            'gemini_available':bool(os.getenv('GEMINI_API_KEY'))}

@app.get('/api/steps')
def steps(): return db.steps()

class StepIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    color: str
    min_pct: float = Field(default=0.5, ge=0.1, le=12)

class StepsIn(BaseModel):
    steps: list[StepIn] = Field(min_length=2,max_length=6)

@app.put('/api/steps')
def update_steps(body: StepsIn):
    s = [x.model_dump() for x in body.steps]
    colors = [x['color'] for x in s]
    if len(colors)!=len(set(colors)) or any(c not in HSV for c in colors):
        raise HTTPException(400,'กรุณาเลือกสีที่รองรับและไม่ซ้ำกัน')
    if sessions:
        raise HTTPException(409,'กรุณาหยุด Live Inspection ก่อนแก้ไข SOP')
    return db.replace_steps(s)

@app.get('/api/stats')
def stats():
    from reporting import snapshot, inspection_records
    data=snapshot(limit=6)
    return {'stats':db.stats(), 'reports':inspection_records()[:6],
            'production':data['stats'], 'generated_at':data['generated_at']}

@app.get('/api/records')
def unified_records():
    from reporting import inspection_records
    return inspection_records()


@app.get('/api/reports')
def reports(): return db.get_reports()

@app.get('/api/reports/{report_id}')
def report(report_id: str):
    r=db.get_report(report_id)
    if r is None: raise HTTPException(404,'ไม่พบรายงาน')
    return r


@app.get('/api/traceability')
def traceability(qr: str | None = Query(default=None, min_length=1, max_length=200),
                 attempt_id: str | None = Query(default=None, min_length=1, max_length=80),
                 key: str | None = Query(default=None, min_length=1, max_length=200)):
    if sum(value is not None for value in (qr, attempt_id, key)) != 1:
        raise HTTPException(400, 'ระบุ QR, attempt ID หรือ key อย่างใดอย่างหนึ่ง')
    matched_attempt = attempt_id
    if key is not None:
        qr = key.strip()
        with db.connect() as c:
            if not c.execute('SELECT 1 FROM flow_jobs WHERE qr=?', (qr,)).fetchone():
                attempt = c.execute('SELECT qr FROM flow_attempts WHERE id=?', (qr,)).fetchone()
                if attempt is None:
                    raise HTTPException(404, 'ไม่พบ QR หรือรอบงานในระบบ')
                qr, matched_attempt = attempt['qr'], key.strip()
    elif attempt_id is not None:
        with db.connect() as c:
            attempt = c.execute('SELECT qr FROM flow_attempts WHERE id=?',
                                (attempt_id.strip(),)).fetchone()
        if attempt is None:
            raise HTTPException(404, 'ไม่พบรอบงานในระบบ')
        qr = attempt['qr']
        matched_attempt = attempt_id.strip()
    if qr is None:
        raise HTTPException(400, 'ไม่พบ QR สำหรับอ่านประวัติ')
    record = db.get_traceability(qr.strip())
    if record is None:
        raise HTTPException(404, 'ไม่พบ QR งานในระบบ')
    record['matched_attempt_id'] = matched_attempt
    return record


def validate_report_qr(qr):
    if not qr:
        return None
    value = qr.strip()
    with db.connect() as c:
        if not c.execute('SELECT 1 FROM flow_jobs WHERE qr=?', (value,)).fetchone():
            raise HTTPException(404, 'ไม่พบ QR งานในระบบ จึงเชื่อมรายงานไม่ได้')
    return value


def validate_report_link(qr, attempt_id, station_id):
    qr = validate_report_qr(qr)
    if attempt_id and not qr:
        raise HTTPException(400, 'ต้องระบุ QR เมื่อต้องการเชื่อมกับรอบงาน')
    if attempt_id:
        with db.connect() as c:
            attempt = c.execute('SELECT qr,station_id FROM flow_attempts WHERE id=?',
                                (attempt_id.strip(),)).fetchone()
        if attempt is None or attempt['qr'] != qr or attempt['station_id'] != station_id:
            raise HTTPException(400, 'รอบงานไม่ตรงกับ QR หรือสเตชั่นที่ระบุ')
        attempt_id = attempt_id.strip()
    return qr, attempt_id

# A demo session retains only its state on server; no face/employee recognition.
sessions: dict[str,dict] = {}

@app.post('/api/live/start')
def live_start(station_id: int = 1, qr: str | None = Query(default=None, max_length=200),
               attempt_id: str | None = Query(default=None, max_length=80)):
    if len(sessions) >= 8: raise HTTPException(429,'จำนวนเซสชัน Live เต็ม')
    station = station_for(station_id)
    qr, attempt_id = validate_report_link(qr, attempt_id, station_id)
    sid = uuid.uuid4().hex[:12]
    sessions[sid] = {'tracker':Tracker(station['steps'], anchor=station['anchor'], require_stability=station.get('require_stability',False),
                                       configuration_version=station['version']),
                     'station':station, 'start':time.monotonic(), 'qr':qr,
                     'attempt_id':attempt_id,
                     'created_at':now(),'evidence':{}}
    return {'id':sid,'sample_every_ms':LIVE_SAMPLE_MS,'steps':station['steps'],
            'station':station}


def decoded_image(payload: bytes):
    if len(payload)>3_000_000: raise HTTPException(413,'ภาพใหญ่เกินไป')
    frame=cv2.imdecode(np.frombuffer(payload,dtype=np.uint8),cv2.IMREAD_COLOR)
    if frame is None: raise HTTPException(400,'อ่านภาพไม่ได้')
    return frame


def remember_evidence(sid, frame, step, found, steps):
    filename=f'{sid}_{step["color"]}.jpg'
    file=EVIDENCE/filename
    if not cv2.imwrite(str(file),annotated(frame,found,steps)):
        raise HTTPException(507,'บันทึกภาพหลักฐานไม่สำเร็จ')
    return '/media/evidence/'+filename

@app.post('/api/live/frame/{sid}')
async def live_frame(sid: str, frame: UploadFile=File(...)):
    if sid not in sessions: raise HTTPException(404,'เซสชันสิ้นสุดแล้ว')
    sess=sessions[sid]
    frame_bytes=await frame.read(3_000_001)
    image=decoded_image(frame_bytes)
    found,new=sess['tracker'].feed(image,time.monotonic()-sess['start'])
    for step in new:
        sess['evidence'][step['color']]=remember_evidence(sid,image,step,found,
                                                           sess['station']['steps'])
    result=sess['tracker'].snapshot()
    result['visible'] = found
    result['evidence'] = sess['evidence']
    return result

@app.post('/api/live/stop/{sid}')
def live_stop(sid: str):
    sess=sessions.pop(sid,None)
    if sess is None: raise HTTPException(404,'เซสชันสิ้นสุดแล้ว')
    result=sess['tracker'].snapshot(final=True, seconds=time.monotonic()-sess['start'])
    result['evidence'] = sess['evidence']
    db.save_report(sid,'live',sess['created_at'],result,qr=sess['qr'],
                   attempt_id=sess['attempt_id'],station_id=sess['station']['id'])
    return {'id':sid, 'qr':sess['qr'], 'attempt_id':sess['attempt_id'],
            'station_id':sess['station']['id'], **result}

MAX_SIZE = 80*1024*1024
EXTS={'.mp4','.mov','.avi','.webm','.mkv'}


def analyze_video(path: Path, sid: str, station: dict):
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError('ไม่สามารถเปิดวิดีโอได้ กรุณาใช้ MP4 (H.264)')
    try:
        fps=cap.get(cv2.CAP_PROP_FPS) or 25
        frames=cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration=frames/fps if fps>0 and frames>0 else 0
        if duration>125: raise ValueError('รองรับวิดีโอยาวไม่เกิน 2 นาที')
        tracker=Tracker(station['steps'], anchor=station['anchor'], require_stability=station.get('require_stability',False),
                        configuration_version=station['version'])
        proof={}
        # Sequential decoding avoids costly seeks and checks up to 12 frames/s.
        # Grab skipped frames without retrieving their decoded pixel arrays.
        frame_index=0; next_sample=0.0
        while frame_index/fps <= 120 and cap.grab():
            t=frame_index/fps
            frame_index+=1
            if t+1e-9 < next_sample:
                continue
            while next_sample <= t+1e-9:
                next_sample += 1.0/VIDEO_SAMPLE_FPS
            ok,frame=cap.retrieve()
            if not ok:continue
            if max(frame.shape[:2])>960:
                h,w=frame.shape[:2]; frame=cv2.resize(frame,(int(w*960/max(w,h)),int(h*960/max(w,h))))
            found,new=tracker.feed(frame,t)
            for s in new:
                proof[s['color']]=remember_evidence(sid,frame,s,found,station['steps'])
        if tracker.frames==0: raise ValueError('อ่านเฟรมจากวิดีโอไม่ได้')
        result=tracker.snapshot(final=True)
        result['evidence']=proof
        result['station']={'id':station['id'],'name':station['name']}
        return result
    finally: cap.release()

@app.post('/api/upload')
async def upload(file: UploadFile=File(...), station_id: int = Form(default=1),
                 qr: str | None = Form(default=None, max_length=200),
                 attempt_id: str | None = Form(default=None, max_length=80)):
    name=Path(file.filename or '').name
    suffix=Path(name).suffix.lower()
    if suffix not in EXTS: raise HTTPException(400,'รองรับไฟล์ MP4 / MOV / AVI / WEBM / MKV')
    sid=uuid.uuid4().hex[:12]
    qr, attempt_id = validate_report_link(qr, attempt_id, station_id)
    station=station_for(station_id)
    dest=UPLOADS/(sid+suffix)
    total=0
    try:
        with dest.open('wb') as f:
            while chunk:=await file.read(1024*1024):
                total+=len(chunk)
                if total>MAX_SIZE: raise HTTPException(413,'ไฟล์ต้องไม่เกิน 80MB')
                f.write(chunk)
        if total==0: raise HTTPException(400,'ไฟล์ว่างเปล่า')
        created=now()
        result=await run_in_threadpool(analyze_video,dest,sid,station)
        db.save_report(sid,'upload',created,result,'/media/uploads/'+dest.name,
                       qr=qr,attempt_id=attempt_id,station_id=station_id)
        return {'id':sid,'qr':qr,'attempt_id':attempt_id,'station_id':station_id,**result,
                'video_url':'/media/uploads/'+dest.name}
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422,str(e))
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally: await file.close()

@app.post('/api/reports/{rid}/ai-review')
async def ai_review(rid: str):
    """Optional semantic AI second opinion; cannot change CV-based pass/fail status."""
    rep=db.get_report(rid)
    if not rep: raise HTTPException(404,'ไม่พบรายงาน')
    evidence=list(rep['result'].get('evidence',{}).values())[:5]
    if not evidence: raise HTTPException(400,'รายงานนี้ยังไม่มีภาพหลักฐานสำหรับให้ AI ตรวจ')

    def review():
        prompt=(
            'คุณคือผู้ช่วยตรวจงานประกอบแบบทดลอง ไม่ใช่ผู้ตัดสินคุณภาพชิ้นงานจริง. '
            'ภาพต่อไปนี้เป็น snapshot ที่ระบบ Computer Vision เก็บเมื่อพบ marker ตามสี. '
            'SOP คือ '+json.dumps([s['name'] for s in rep['result']['steps']],ensure_ascii=False)+'. '
            'เหตุการณ์: '+json.dumps(rep['result']['events'],ensure_ascii=False)+'. '
            'อธิบายเป็นภาษาไทยสั้น ๆ ว่ามองเห็นอะไรในภาพ และความไม่แน่นอนของการตรวจลำดับขั้นตอน. '
            'ห้ามกล่าวว่าการกระทำผ่านหรือผิดแน่นอนหากภาพนิ่งพิสูจน์ลำดับไม่ได้. '
            'แยกเป็นหัวข้อ ข้อสังเกต, ข้อจำกัด, สิ่งที่ควรตรวจซ้ำ.\n'
        )
        paths = []
        for uri in evidence:
            filename = Path(uri).name
            image_path = (EVIDENCE / filename).resolve()
            if image_path.parent != EVIDENCE.resolve() or not image_path.is_file():
                continue
            paths.append(image_path)
        return review_images(prompt, paths)
    try:
        return await run_in_threadpool(review)
    except ValueError as e:
        raise HTTPException(400,str(e))
    except Exception as e:
        raise HTTPException(502,'AI Review ไม่สำเร็จ: '+str(e)[:180])
