"""Real HTTP + verified HTTPS + streaming camera smoke test, isolated database.

Run from the project root after installing requirements-mobile.txt.
"""
import base64
import json
import socket
import ssl
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import cv2
import httpx
import numpy as np
import uvicorn
import db
import cameras
import mobile_gateway
from main import app


def serve(application,secure=False):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(32)
    port=listener.getsockname()[1]
    config=uvicorn.Config(application,log_level='warning',
        ssl_certfile=str(ROOT/'.certs/server.pem') if secure else None,
        ssl_keyfile=str(ROOT/'.certs/server-key.pem') if secure else None)
    server=uvicorn.Server(config)
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
    for _ in range(200):
        if server.started:return server,thread,port
        if not thread.is_alive():raise RuntimeError('Test server failed to start')
        time.sleep(.05)
    raise RuntimeError('Test server startup timeout')


def main():
    runs=ROOT/'artifacts'/'test-runs';runs.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='camera-network-',dir=runs) as name:
        temp=Path(name).resolve();assert temp.parent==runs.resolve()
        db.DB=temp/'isolated.db';cameras.MEDIA=temp;cameras.latest={}
        backend,worker,port=serve(app)
        mobile_gateway.BACKEND=f'http://127.0.0.1:{port}'
        gateway=gate_thread=None
        try:
            gateway,gate_thread,secure_port=serve(mobile_gateway.app,secure=True)
            context=ssl.create_default_context(cafile=str(ROOT/'.certs/sopvision-ca.crt'))
            with httpx.Client(base_url=f'https://127.0.0.1:{secure_port}',verify=context,trust_env=False,timeout=10) as phone:
                # Exercise real authentication/CSRF rather than bypassing it.
                import auth
                setup=phone.post('/api/auth/setup',json={'username':'networkadmin','display_name':'Network Test',
                    'password':'TestOnly-Password-739','code':auth.setup_path().read_text().strip()})
                setup.raise_for_status()
                phone.headers['X-CSRF-Token']=phone.get('/api/auth/me').json()['csrf_token']
                cid='network-camera-123456';token='camera-network-private-token-123456'
                response=phone.post('/api/cameras/open',json={'id':cid,'token':token,'source':'worker','station_id':1,'operator':'TEST-NETWORK','mime_type':'video/mp4'})
                response.raise_for_status()
                def send(value,sequence):
                    ok,jpg=cv2.imencode('.jpg',np.full((120,160,3),value,dtype=np.uint8));assert ok
                    response=phone.post(f'/api/cameras/{cid}/frame/{sequence}',headers={'X-Camera-Key':token},files={'frame':('frame.jpg',jpg.tobytes(),'image/jpeg')})
                    response.raise_for_status()
                send(70,0)
                with phone.stream('GET','/api/cameras/events') as stream:
                    stream.raise_for_status();assert 'text/event-stream' in stream.headers['content-type']
                    lines=stream.iter_lines()
                    first=next(line for line in lines if line.startswith('data: '))
                    frame=json.loads(first[6:])['frames'][0];assert frame['id']==cid and frame['sequence']==0
                    jpg=base64.b64decode(frame['jpeg']);assert cv2.imdecode(np.frombuffer(jpg,dtype=np.uint8),cv2.IMREAD_COLOR) is not None
                    send(140,1)
                    second=next(line for line in lines if line.startswith('data: '))
                    assert json.loads(second[6:])['frames'][0]['sequence']==1
                video=temp/'synthetic.mp4'
                writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,120));assert writer.isOpened()
                for n in range(12):writer.write(np.full((120,160,3),n*10,dtype=np.uint8))
                writer.release();payload=video.read_bytes()
                response=phone.post(f'/api/cameras/{cid}/segments/0/chunks/0',headers={'X-Camera-Key':token},files={'chunk':('clip.mp4',payload,'video/mp4')});response.raise_for_status()
                response=phone.post(f'/api/cameras/{cid}/segments/0/finish',headers={'X-Camera-Key':token},json={'chunks':1,'bytes':len(payload)});response.raise_for_status()
                clips=phone.get('/api/cameras/archive',params={'q':'TEST-NETWORK'}).json();assert clips['total']==1
                playback=phone.get(clips['segments'][0]['video_url'],headers={'Range':'bytes=0-63'})
                assert playback.status_code==206 and playback.content==payload[:64]
                assert phone.get('/api/flow/admin').json()['stats']['total_attempts']==0
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False) as desktop:
                    desktop.post('/api/auth/login',json={'username':'networkadmin','password':'TestOnly-Password-739'}).raise_for_status()
                    assert desktop.get('/api/cameras').json()['cameras'][0]['id']==cid
                phone.post(f'/api/cameras/{cid}/close',json={'token':token}).raise_for_status()
                assert phone.get('/api/cameras/archive').json()['segments'][0]['state']=='complete'
            print('PASS: verified HTTPS, two live frame updates over streaming proxy, idle-camera archive, range playback, shared backend; no production data created')
        finally:
            if gateway:gateway.should_exit=True;gate_thread.join(5)
            backend.should_exit=True;worker.join(5)


if __name__=='__main__':main()
