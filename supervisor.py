"""Supervisor portal: approval and archived video only."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
import auth
import db

router = APIRouter(tags=['Supervisor'])


def authorize():
    account = auth.user()
    if not account or account['role'] not in ('admin','supervisor'):
        raise HTTPException(403, 'เฉพาะหัวหน้างานหรือแอดมิน')


@router.get('/supervisor')
def page():
    authorize()
    return FileResponse(auth.ROOT/'static/supervisor.html')


@router.get('/api/supervisor/recordings')
def recordings(response: Response, q: str = Query(default='',max_length=300),
               station_id: int | None = Query(default=None,ge=1,le=3),
               offset: int = Query(default=0,ge=0), limit: int = Query(default=20,ge=1,le=50)):
    authorize()
    response.headers['Cache-Control']='no-store'
    clauses=['a.ended_at IS NOT NULL', 'a.video_url IS NOT NULL']; args=[]
    if q.strip():
        clauses.append('(instr(a.qr,?)>0 OR instr(coalesce(j.source_qr,\'\'),?)>0 OR instr(a.operator,?)>0)')
        args.extend([q.strip()]*3)
    if station_id is not None:
        clauses.append('a.station_id=?');args.append(station_id)
    sql=' FROM flow_attempts a JOIN flow_jobs j ON j.qr=a.qr WHERE '+' AND '.join(clauses)
    with db.connect() as c:
        c.execute('BEGIN')
        total=c.execute('SELECT count(*)'+sql,args).fetchone()[0]
        rows=c.execute('''SELECT a.id,a.qr,j.source_qr,j.is_test,a.station_id,a.operator,a.state,
            a.started_at,a.ended_at,a.video_url'''+sql+' ORDER BY a.started_at DESC,a.rowid DESC LIMIT ? OFFSET ?',
            [*args,limit,offset]).fetchall()
    items=[]
    import production
    for row in rows:
        item=dict(row)
        media=Path(production.RECORDINGS).resolve()
        file=(media/Path(item['video_url']).name).resolve()
        item['available']=item['video_url'].startswith('/media/recordings/') and file.is_relative_to(media) and file.is_file() and file.stat().st_size>0
        items.append(item)
    return {'recordings':items,'total':total,'offset':offset,'limit':limit}


@router.post('/api/supervisor/qr/decode')
async def decode_search_qr(frame: UploadFile = File(...)):
    authorize()
    payload=await frame.read(3_000_001)
    if not payload:
        raise HTTPException(400,'ไม่ได้รับภาพ QR')
    def decode():
        import cv2
        from main import decoded_image
        from production import clean_qr
        image=decoded_image(payload)
        value, _, _=cv2.QRCodeDetector().detectAndDecode(image)
        return {'qr':clean_qr(value) if value else None}
    return await run_in_threadpool(decode)
