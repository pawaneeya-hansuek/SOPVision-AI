"""Continuous camera monitoring, independent of production attempts."""
import asyncio
import base64
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import cameras
import db
from main import app


@pytest.fixture
def camera_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db,'DB',tmp_path/'camera.db')
    monkeypatch.setattr(cameras,'MEDIA',tmp_path)
    monkeypatch.setattr(cameras,'latest',{})
    with TestClient(app) as client:
        from auth_helpers import bootstrap
        bootstrap(client)
        yield client


def open_cam(client, cid='camera-unique-123456', source='worker', station=1):
    body={'id':cid,'token':'secret-token-for-camera-upload-123456789','source':source,
          'station_id':station,'operator':'CAMERA-EMP','device_label':'Test camera','mime_type':'video/mp4'}
    response=client.post('/api/cameras/open',json=body)
    assert response.status_code==200,response.text
    return body


def image(value=70):
    frame=np.full((120,160,3),value,dtype=np.uint8)
    ok,encoded=cv2.imencode('.jpg',frame)
    assert ok
    return encoded.tobytes()


def upload(client,body,segment=0,sequence=0,data=b'video'*200):
    return client.post(f'/api/cameras/{body["id"]}/segments/{segment}/chunks/{sequence}',
                       headers={'X-Camera-Key':body['token']},files={'chunk':('part',data)})


def test_camera_visible_without_starting_any_workpiece(camera_client):
    c=camera_client;body=open_cam(c)
    assert c.get('/api/flow/admin').json()['stats']['total_attempts']==0
    assert c.get('/api/cameras').json()['cameras'][0]['online'] is False
    response=c.post(f'/api/cameras/{body["id"]}/frame/0',headers={'X-Camera-Key':body['token']},files={'frame':('image.jpg',image())})
    assert response.status_code==200
    row=c.get('/api/cameras').json()['cameras'][0]
    assert row['online'] and row['source']=='worker' and row['station_id']==1
    assert row['operator']=='CAMERA-EMP'
    assert 'token_hash' not in row and 'token' not in row


def test_camera_work_links_and_traceability_are_explicit(camera_client):
    c = camera_client
    qr = 'TRACEABILITY-WORK-001'
    attempt = c.post('/api/flow/start', json={
        'qr': qr, 'station_id': 1, 'operator': 'EMP-TRACE', 'mime_type': 'video/webm'})
    assert attempt.status_code == 200, attempt.text
    attempt_id = attempt.json()['id']
    body = open_cam(c)
    path = f'/api/cameras/{body["id"]}/work-link'
    headers = {'X-Camera-Key': body['token']}

    mismatch = c.post(path, headers=headers,
                      json={'qr': 'DIFFERENT-WORK', 'attempt_id': attempt_id})
    assert mismatch.status_code == 400
    linked = c.post(path, headers=headers,
                    json={'qr': qr, 'attempt_id': attempt_id})
    assert linked.status_code == 200, linked.text
    segment_time = cameras.now()
    with db.connect() as conn:
        conn.execute('''INSERT INTO camera_segments
            (camera_id,segment_index,started_at,ended_at,state,chunks,bytes)
            VALUES(?,0,?,?,'complete',1,42)''', (body['id'], segment_time, segment_time))
    archive = c.get('/api/cameras/archive', params={'q': qr})
    assert archive.status_code == 200, archive.text
    assert archive.json()['segments'][0]['related_qrs'] == qr

    result = c.get('/api/traceability', params={'qr': qr})
    assert result.status_code == 200, result.text
    record = result.json()
    assert [row['id'] for row in record['attempts']] == [attempt_id]
    assert record['camera_links'][0]['qr'] == qr
    assert record['camera_links'][0]['attempt_id'] == attempt_id
    by_attempt = c.get('/api/traceability', params={'attempt_id': attempt_id})
    assert by_attempt.status_code == 200
    assert by_attempt.json()['matched_attempt_id'] == attempt_id
    assert c.get('/api/traceability', params={'key': attempt_id}).json()['job']['qr'] == qr

    invalid_report_link = c.post(
        f'/api/live/start?station_id=1&qr={qr}&attempt_id=missing-attempt')
    assert invalid_report_link.status_code == 400
    live = c.post(f'/api/live/start?station_id=1&qr={qr}&attempt_id={attempt_id}')
    assert live.status_code == 200, live.text
    assert c.post(f'/api/live/stop/{live.json()["id"]}').status_code == 200
    record = c.get('/api/traceability', params={'qr': qr}).json()
    assert record['reports'][0]['qr'] == qr
    assert record['reports'][0]['attempt_id'] == attempt_id

    unlinked = c.post(path, headers=headers,
                      json={'qr': None, 'attempt_id': attempt_id})
    assert unlinked.status_code == 200, unlinked.text
    assert c.get('/api/traceability', params={'qr': qr}).json()['camera_links'][0]['unlinked_at']


def test_traceability_does_not_guess_unlinked_legacy_reports(camera_client):
    report_result = {'elapsed': 1.0, 'status': 'review', 'verified': 0,
                     'total': 1, 'issues': 1}
    db.save_report('LEGACY-REPORT-UNLINKED', 'live', '2026-01-01T00:00:00+00:00',
                   report_result)
    qr = 'TRACEABILITY-WORK-LEGACY'
    attempt = camera_client.post('/api/flow/start', json={
        'qr': qr, 'station_id': 1, 'operator': 'EMP-LEGACY', 'mime_type': 'video/webm'})
    assert attempt.status_code == 200, attempt.text
    result = camera_client.get('/api/traceability', params={'qr': qr})
    assert result.status_code == 200
    assert result.json()['reports'] == []
    assert 'ไม่ถูกจับคู่โดยคาดเดา' in result.json()['legacy_note']


def test_traceability_migration_backup_preserves_old_rows(tmp_path, monkeypatch):
    legacy_db = tmp_path / 'legacy.db'
    monkeypatch.setattr(db, 'DB', legacy_db)
    with sqlite3.connect(legacy_db) as conn:
        conn.execute('CREATE TABLE reports(id TEXT, mode TEXT)')
        conn.execute('CREATE TABLE camera_sessions(id TEXT, source TEXT)')
        conn.execute("INSERT INTO reports VALUES('old-report','live')")
        conn.execute("INSERT INTO camera_sessions VALUES('old-camera','worker')")

    db.backup_before_traceability_change()
    backups = list(tmp_path.glob('legacy.pre-traceability-*.bak'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('SELECT * FROM reports').fetchone() == ('old-report', 'live')
        assert conn.execute('SELECT * FROM camera_sessions').fetchone() == ('old-camera', 'worker')


def test_preview_idempotence_authentication_and_old_frames(camera_client):
    c=camera_client;body=open_cam(c)
    path=f'/api/cameras/{body["id"]}/frame/2'
    args={'headers':{'X-Camera-Key':body['token']},'files':{'frame':('frame.jpg',image())}}
    assert c.post(path,**args).status_code==200
    assert c.post(path,**args).json()['duplicate']
    assert c.post(path,headers=args['headers'],files={'frame':('frame.jpg',image(100))}).status_code==409
    assert c.post(path.replace('/2','/1'),**args).status_code==409
    assert c.post(path,files=args['files']).status_code==403
    assert c.post(path.replace('/2','/3'),headers=args['headers'],files={'frame':('bad',b'bad')}).status_code==400


def test_live_stream_contains_actual_camera_frames(camera_client):
    c=camera_client;body=open_cam(c)
    c.post(f'/api/cameras/{body["id"]}/frame/0',headers={'X-Camera-Key':body['token']},files={'frame':('f.jpg',image())})
    async def first_frames():
        response=await cameras.events()
        try:
            payload=await anext(response.body_iterator)
            assert payload.startswith('retry: ')
            payload=await anext(response.body_iterator)
            event=json.loads(payload.removeprefix('data: ').strip())
            assert event['frames'][0]['id']==body['id']
            jpg=base64.b64decode(event['frames'][0]['jpeg'])
            assert cv2.imdecode(np.frombuffer(jpg,dtype=np.uint8),cv2.IMREAD_COLOR) is not None
        finally:
            await response.body_iterator.aclose()
        response=await cameras.live(body['id'])
        try:
            payload=await anext(response.body_iterator)
            assert b'Content-Type: image/jpeg' in payload and b'\xff\xd8' in payload
        finally:
            await response.body_iterator.aclose()
    asyncio.run(first_frames())


def test_complete_archive_is_playable_and_supports_range(camera_client,tmp_path):
    c=camera_client;body=open_cam(c)
    original=tmp_path/'original.mp4'
    writer=cv2.VideoWriter(str(original),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,120))
    assert writer.isOpened()
    for n in range(12):
        writer.write(np.full((120,160,3),n*10,dtype=np.uint8))
    writer.release();data=original.read_bytes()
    # Upload independently of QR work, in two pieces, then acknowledge final byte count.
    half=len(data)//2
    assert upload(c,body,data=data[:half]).status_code==200
    assert upload(c,body,sequence=1,data=data[half:]).status_code==200
    path=f'/api/cameras/{body["id"]}/segments/0/finish'
    finish={'chunks':2,'bytes':len(data)}
    assert c.post(path,headers={'X-Camera-Key':body['token']},json=finish).status_code==200
    assert c.post(path,headers={'X-Camera-Key':body['token']},json=finish).status_code==200
    archive=c.get('/api/cameras/archive').json()
    assert archive['total']==1
    row=archive['segments'][0]
    assert row['state']=='complete' and row['available'] and row['chunks']==2
    playback=c.get(row['video_url'])
    assert playback.status_code==200 and playback.headers['content-type']=='video/mp4'
    assert playback.content[4:8]==b'ftyp' and b'avc1' in playback.content
    ranged=c.get(row['video_url'],headers={'Range':'bytes=0-39'})
    assert ranged.status_code==206 and ranged.content==playback.content[:40]
    saved=cameras.segment_file(body['id'],0,body['mime_type'])
    assert saved.read_bytes()==data
    cap=cv2.VideoCapture(str(saved))
    try:
        ok,frame=cap.read();assert ok and frame.shape[:2]==(120,160)
    finally:cap.release()
    assert c.get('/api/flow/admin').json()['stats']['total_attempts']==0


def test_video_duplicates_out_of_order_and_incomplete_finish(camera_client):
    c=camera_client;body=open_cam(c)
    assert upload(c,body,sequence=1).status_code==409
    assert upload(c,body).status_code==200
    assert upload(c,body).json()['duplicate']
    assert upload(c,body,data=b'different'*100).status_code==409
    row=c.get('/api/cameras/archive').json()['segments'][0]
    assert row['chunks']==1 and row['bytes']==1000
    path=f'/api/cameras/{body["id"]}/segments/0/finish'
    assert c.post(path,headers={'X-Camera-Key':body['token']},json={'chunks':2,'bytes':1000}).status_code==409
    assert c.get(f'/api/cameras/{body["id"]}/segments/0/video').status_code==409


def test_close_keeps_complete_and_partial_clips_distinct(camera_client):
    c=camera_client;body=open_cam(c)
    upload(c,body)
    response=c.post(f'/api/cameras/{body["id"]}/segments/0/finish',headers={'X-Camera-Key':body['token']},json={'chunks':1,'bytes':1000})
    assert response.status_code==200,response.text
    upload(c,body,segment=1)
    close=f'/api/cameras/{body["id"]}/close'
    assert c.post(close,json={'token':'wrong'}).status_code==403
    assert c.post(close,json={'token':body['token']}).status_code==200
    assert c.post(close,json={'token':body['token']}).status_code==200
    assert not c.get('/api/cameras').json()['cameras']
    clips=c.get('/api/cameras/archive').json()['segments']
    assert {r['state'] for r in clips}=={'complete','partial'}
    assert all(r['available'] for r in clips)
    assert upload(c,body,segment=2).status_code==409
    assert c.post('/api/cameras/open',json=body).status_code==409


def test_restart_preserves_archives_and_marks_unfinished_partial(camera_client):
    c=camera_client;body=open_cam(c)
    upload(c,body)
    db.initialize()
    row=c.get('/api/cameras/archive').json()['segments'][0]
    assert row['state']=='partial' and row['camera_state']=='interrupted'
    assert row['error']=='เซิร์ฟเวอร์เริ่มใหม่'
    assert c.get(row['video_url']).status_code==200
    assert not c.get('/api/cameras').json()['cameras']


def test_offline_is_never_presented_as_live(camera_client):
    c=camera_client;body=open_cam(c)
    c.post(f'/api/cameras/{body["id"]}/frame/0',headers={'X-Camera-Key':body['token']},files={'frame':('f.jpg',image())})
    old=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()
    with db.connect() as conn:
        conn.execute('UPDATE camera_sessions SET frame_at=?',(old,))
    assert c.get('/api/cameras').json()['cameras'][0]['online'] is False
    upload(c,body)
    older=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
    with db.connect() as conn:
        conn.execute('UPDATE camera_sessions SET last_seen=?',(older,))
    assert not c.get('/api/cameras').json()['cameras']
    assert c.get('/api/cameras/archive').json()['segments'][0]['state']=='partial'
    assert body['id'] not in cameras.latest


@pytest.mark.parametrize('source,station',[('worker',1),('flow',2),('live',None),('qr',3)])
def test_all_application_camera_sources(camera_client,source,station):
    c=camera_client;body=open_cam(c,source=source,station=station)
    upload(c,body)
    assert c.get('/api/cameras').json()['cameras'][0]['source']==source
    assert c.get('/api/cameras/archive',params={'source':source}).json()['total']==1
    if station:
        assert c.get('/api/cameras/archive',params={'station_id':station}).json()['total']==1
    assert c.get('/api/cameras/archive',params={'q':'NO-SUCH-CAMERA'}).json()['total']==0
    assert c.get('/api/cameras/archive',params={'source':'invented'}).status_code==422
    assert c.get('/api/cameras/archive',params={'since':'2026-10-20T00:00:00'}).status_code==400
    assert c.get('/api/cameras/archive',params={'since':'2026-10-21T00:00:00Z','until':'2026-10-20T00:00:00Z'}).status_code==400


def test_disk_error_does_not_acknowledge_unsaved_recording(camera_client,monkeypatch):
    c=camera_client;body=open_cam(c)
    with monkeypatch.context() as patch:
        patch.setattr(cameras.os,'fsync',lambda _:(_ for _ in ()).throw(OSError('disk failed')))
        with pytest.raises(OSError):upload(c,body)
    assert c.get('/api/cameras/archive').json()['total']==0
    assert cameras.segment_file(body['id'],0,body['mime_type']).stat().st_size==0
    assert upload(c,body).status_code==200
