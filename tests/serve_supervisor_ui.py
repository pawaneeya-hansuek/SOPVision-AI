"""Isolated UI fixture with synthetic video and test-only accounts."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.test-deps'))
import tempfile
import json
import cv2
import numpy as np
import uvicorn
from starlette.staticfiles import StaticFiles
from playback import RecordedMedia
import playback
import db, auth, production, cameras
import main

if __name__=='__main__':
    runs=ROOT/'artifacts'/'test-runs';runs.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='supervisor-',dir=runs) as name:
        folder=Path(name);media=folder/'media';media.mkdir()
        playback.CACHE=media/'playback'
        db.DB=folder/'ui.db';production.RECORDINGS=media/'recordings';production.RECORDINGS.mkdir()
        production.EVIDENCE=media/'evidence';production.EVIDENCE.mkdir()
        cameras.MEDIA=media/'cameras';cameras.MEDIA.mkdir()
        for route in main.app.routes:
            if getattr(route,'path',None)=='/media':route.app=RecordedMedia(directory=media)
        db.initialize()
        with db.connect() as c:
            for username,role in [('uiadmin','admin'),('uihead','supervisor')]:
                c.execute('INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                          (username,username,auth.password_hash('HeadOnly-Password-915' if role=='supervisor' else 'TestOnly-Password-739'),role,auth.now()))
            c.execute('INSERT INTO flow_jobs(qr,created_at) VALUES(?,?)',('UI-RETRY-001',auth.now()))
            c.execute('''INSERT INTO flow_attempts(id,qr,station_id,operator,state,started_at,ended_at,video_url,result_json)
                VALUES(?, ?,1,'STATION-1','interrupted',?,?,?,?)''',('ui-attempt-001','UI-RETRY-001',auth.now(),auth.now(),
                '/media/recordings/ui-attempt-001.webm',json.dumps({'status':'review','error':'ตรวจขั้นตอนไม่ครบ ต้องอนุญาตก่อนสแกนซ้ำ','steps':[]})))
        video=production.RECORDINGS/'ui-attempt-001.webm'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'VP80'),10,(320,568));assert writer.isOpened()
        frame=np.full((568,320,3),(52,35,20),dtype=np.uint8)
        cv2.rectangle(frame,(20,30),(300,185),(70,170,60),-1)
        cv2.rectangle(frame,(20,210),(300,365),(60,70,210),-1)
        cv2.rectangle(frame,(20,390),(300,540),(210,120,40),-1)
        cv2.putText(frame,'CAMERA TEST',(30,110),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
        for _ in range(20):writer.write(frame)
        writer.release()
        with (folder/'portrait.y4m').open('wb') as output:
            output.write(b'YUV4MPEG2 W320 H568 F10:1 Ip A1:1 C420jpeg\n')
            yuv=cv2.cvtColor(frame,cv2.COLOR_BGR2YUV_I420).tobytes()
            for _ in range(20):output.write(b'FRAME\n'+yuv)
        qr=cv2.QRCodeEncoder_create().encode('UI-RETRY-001')
        qr=cv2.copyMakeBorder(qr,4,4,4,4,cv2.BORDER_CONSTANT,value=255)
        qr=cv2.resize(qr,None,fx=8,fy=8,interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(folder/'search-qr.png'),qr)
        (ROOT/'.test-supervisor-ready.json').write_text(json.dumps({'portrait':str(folder/'portrait.y4m'),'qr':str(folder/'search-qr.png')}),encoding='utf-8')
        try:uvicorn.run(main.app,host='127.0.0.1',port=8766,log_level='warning')
        finally:(ROOT/'.test-supervisor-ready.json').unlink(missing_ok=True)
