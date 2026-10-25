"""Browser-compatible, seekable copies; original recording evidence is untouched."""
from pathlib import Path
import hashlib
import os
import subprocess
import threading
import uuid

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'media'/'playback'
conversion_lock=threading.Lock()


def browser_video(source: Path) -> Path:
    source=Path(source).resolve()
    with source.open('rb') as stream:header=stream.read(16)
    # Leave legacy non-video fixtures/downloads unchanged; real browser recordings
    # use EBML (WebM) or ISO BMFF (MP4).
    if not (header.startswith(b'\x1aE\xdf\xa3') or header[4:8]==b'ftyp'):
        return source
    stat=source.stat()
    key=hashlib.sha256(f'{source}|{stat.st_size}|{stat.st_mtime_ns}|h264-v1'.encode()).hexdigest()
    target=CACHE/(key+'.mp4')
    if target.is_file() and target.stat().st_size:return target
    with conversion_lock:
        if target.is_file() and target.stat().st_size:return target
        binaries=sorted((ROOT/'.media-deps'/'imageio_ffmpeg'/'binaries').glob('ffmpeg*.exe'))
        if (ROOT/'.media-tools'/'ffmpeg.exe').is_file():binaries.append(ROOT/'.media-tools'/'ffmpeg.exe')
        if not binaries:raise HTTPException(503,'ส่วนเตรียมวิดีโอยังไม่พร้อม กรุณาแจ้งแอดมิน')
        CACHE.mkdir(parents=True,exist_ok=True)
        temporary=CACHE/(key+'.'+uuid.uuid4().hex+'.tmp.mp4')
        try:
            result=subprocess.run([str(binaries[-1]),'-hide_banner','-loglevel','error','-y',
                '-fflags','+genpts','-i',str(source),'-map','0:v:0','-map','0:a?',
                '-vf',"scale='min(1280,iw)':-2",'-c:v','libx264','-preset','ultrafast',
                '-crf','23','-pix_fmt','yuv420p','-threads','2','-c:a','aac',
                '-movflags','+faststart','-avoid_negative_ts','make_zero',str(temporary)],
                capture_output=True,timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if result.returncode or not temporary.is_file() or not temporary.stat().st_size:
                raise HTTPException(422,'ไฟล์ต้นฉบับไม่สมบูรณ์ ไม่สามารถเตรียมวิดีโอสำหรับเล่นได้')
            os.replace(temporary,target)
        except subprocess.TimeoutExpired:
            raise HTTPException(503,'เตรียมวิดีโอยังไม่เสร็จ กรุณาลองเปิดอีกครั้ง')
        finally:
            temporary.unlink(missing_ok=True)
    return target


def video_response(source: Path):
    target=browser_video(source)
    return FileResponse(target,media_type='video/mp4' if target.suffix=='.mp4' else 'video/webm',
                        filename=source.stem+target.suffix,content_disposition_type='inline',
                        headers={'Cache-Control':'private, no-store'})


class RecordedMedia(StaticFiles):
    async def get_response(self,path,scope):
        if Path(path).parts and Path(path).parts[0]=='recordings' and Path(path).suffix.lower() in ('.webm','.mp4'):
            resolved,stat=await run_in_threadpool(self.lookup_path,path)
            if stat and Path(resolved).is_file():
                return await run_in_threadpool(video_response,Path(resolved))
        return await super().get_response(path,scope)
