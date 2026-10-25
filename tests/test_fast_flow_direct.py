"""Real route handlers/storage, without HTTP transport or camera hardware."""
from tempfile import SpooledTemporaryFile
import time
import cv2
import pytest
from fastapi import HTTPException, UploadFile
import db
import production
from test_fast_tracking import frame


@pytest.fixture
def station(tmp_path, monkeypatch):
    monkeypatch.setattr(db,'DB',tmp_path/'flow.db')
    monkeypatch.setattr(production,'RECORDINGS',tmp_path)
    monkeypatch.setattr(production,'EVIDENCE',tmp_path)
    monkeypatch.setattr(production,'active',{})
    db.initialize()
    start=production.start_work(production.Start(qr='FAST-TEST',station_id=1,operator='TEST'))
    assert start['sample_every_ms']==80
    return start['id']


def feed(sid,t,*colors):
    _,encoded=cv2.imencode('.jpg',frame(*colors))
    production.active[sid]['started']=time.monotonic()-t
    return run_upload(production.feed_frame,encoded.tobytes(),'test.jpg',sid)


def hold(sid,start,end,*colors):
    result=None
    for index in range(round((end-start)*10)+1):
        result=feed(sid,start+index/10,*colors)
    return result


def run_upload(handler,data,filename,*args):
    with SpooledTemporaryFile(max_size=3_000_000) as stream:
        stream.write(data);stream.seek(0)
        return run_in_memory(handler(*args,UploadFile(stream,filename=filename)))


def run_in_memory(coro):
    import asyncio
    return asyncio.run(coro)


def recording(sid):
    run_upload(production.recording_chunk,b'x'*400,'test.webm',sid,0)


def test_fast_flow_saves_optional_recording_and_unlocks_next_station(station):
    hold(station,0,.9,'green')
    hold(station,1,1.9,'green','red')
    recording(station)
    result=production.finish_work(station)
    assert result['state']=='passed' and result['can_handoff']
    assert result['job']['stations'][1]['state']=='ready'


def test_occluded_step_is_remembered_by_route(station):
    hold(station,0,.9,'green')
    hidden=feed(station,1.0)
    assert hidden['steps'][0]['temporarily_hidden']
    assert hidden['verified']==1
    hold(station,1.1,2.0,'green','red')
    recording(station)
    assert production.finish_work(station)['state']=='passed'


def test_wrong_order_is_quarantined(station):
    assert hold(station,0,.9,'red')['quarantined']
    recording(station)
    result=production.finish_work(station)
    assert result['state']=='blocked' and not result['can_handoff']


def test_fast_flow_without_video_unlocks_after_color_sequence_passes(station):
    hold(station,0,.9,'green')
    hold(station,1,1.9,'green','red')
    result=production.finish_work(station)
    assert result['state']=='passed' and result['can_handoff']
    assert result['inspection']['recording_error']
