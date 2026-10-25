"""Preserve step evidence when Wi-Fi delivers several captured frames at once."""
import json
import time
import cv2
import pytest
import production
from vision import Tracker
from test_fast_tracking import STEPS, ANCHOR, frame
from test_production_flow import client, start
from test_station_access import enter
from pathlib import Path


def encoded(colors):
    ok, raw=cv2.imencode('.jpg',frame(*colors));assert ok
    return raw.tobytes()


def batch(c,sid,colors,times,arrival):
    production.active[sid]['started']=time.monotonic()-arrival
    return c.post('/api/flow/frame/'+sid,
                  files=[('frame',('frame.jpg',encoded(item),'image/jpeg')) for item in colors],
                  data={'captured_ms':json.dumps(times)})


def test_slow_continuous_frames_are_not_treated_as_occlusion():
    tr=Tracker(STEPS,anchor=ANCHOR,require_stability=False)
    tr.feed(frame('green'),.1);tr.feed(frame('green'),1.1)
    assert tr.snapshot()['steps'][0]['status']=='passed'
    tr.feed(frame('green','red'),2.1);tr.feed(frame('green','red'),3.1)
    assert tr.snapshot(final=True)['status']=='pass'


def test_one_green_frame_then_one_red_frame_immediately_completes(client):
    sid=start(client,'INSTANT-COLOR',1).json()['id']
    first=batch(client,sid,[('green',)],[0],.1)
    assert first.status_code==200,first.text
    assert first.json()['verified']==1
    second=batch(client,sid,[('green','red')],[80],.2)
    assert second.status_code==200,second.text
    assert second.json()['verified']==2
    assert second.json()['events'][1]['confirmed_at']==.08


def test_slow_first_upload_does_not_make_catchup_batch_look_future_dated(client):
    sid=start(client,'VARIABLE-WIFI-LATENCY',1).json()['id']
    assert batch(client,sid,[('green',)],[0],2).status_code==200
    # Frames captured while the initial upload was in flight arrive together.
    second=batch(client,sid,[('green',),('green','red')],[100,1900],2.1)
    assert second.status_code==200,second.text
    assert second.json()['verified']==2 and not second.json()['quarantined']


def test_camera_setup_delay_does_not_reject_valid_ordered_frames(client):
    sid=start(client,'DELAYED-CAMERA-EPOCH',1).json()['id']
    first=batch(client,sid,[('green',)],[100],25)
    assert first.status_code==200,first.text
    assert first.json()['verified']==1
    second=batch(client,sid,[('red',)],[200],25.1)
    assert second.status_code==200,second.text
    assert second.json()['verified']==2


def test_user_phone_clip_passes_with_hands_moving_and_batched_delivery(client):
    """Camera area from 814302620.999548.mp4, 10.8–15.8s, without retouching."""
    video=Path(__file__).parent/'fixtures'/'phone-20261022-assembly.mp4'
    sid=start(client,'PHONE-20261022-REGRESSION',1).json()['id']
    cap=cv2.VideoCapture(str(video));frames=[]
    try:
        while True:
            ok,img=cap.read()
            if not ok:break
            ok,data=cv2.imencode('.jpg',img);assert ok
            frames.append(data.tobytes())
    finally:
        cap.release()
    assert len(frames)==51
    first_complete=None
    for offset in range(0,len(frames),10):
        items=frames[offset:offset+10]
        production.active[sid]['started']=time.monotonic()-(offset/10+1.5)
        response=client.post('/api/flow/frame/'+sid,
            files=[('frame',('camera.jpg',raw,'image/jpeg')) for raw in items],
            data={'captured_ms':json.dumps([(offset+n)*100 for n in range(len(items))])})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['processed_frames']==len(items)
        assert (result['frame_width'],result['frame_height'])==(318,570)
        assert not result['quarantined'],result
        if result['verified']==2 and first_complete is None:first_complete=result['elapsed']
    assert first_complete is not None and first_complete<=3.5
    assert [event['color'] for event in result['events']]==['green','red']
    assert client.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.mp4',video.read_bytes())}).status_code==200
    final=client.post('/api/flow/finish/'+sid,files={'frame':('final.jpg',frames[-1],'image/jpeg')})
    assert final.status_code==200,final.text
    assert final.json()['state']=='passed' and final.json()['can_handoff'],final.json()


def test_guest_batches_confirm_steps_and_final_handoff(client):
    c=client;c.cookies.clear();enter(c)
    sid=start(c,'BATCH-NETWORK-REGRESSION',1).json()['id']
    result=batch(c,sid,[('green',)]*6,list(range(0,600,100)),1.5)
    assert result.status_code==200,result.text
    assert result.json()['verified']==1 and result.json()['processed_frames']==6
    result=batch(c,sid,[('green','red')]*6,list(range(600,1200,100)),2.5)
    assert result.status_code==200,result.text
    assert result.json()['verified']==2 and not result.json()['quarantined']
    # Fresh final frame is still required before handoff.
    result=c.post('/api/flow/frame/'+sid,files={'frame':('final.jpg',encoded(('green','red')),'image/jpeg')})
    assert result.status_code==200,result.text
    c.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'recorded-evidence'*100)})
    result=c.post('/api/flow/finish/'+sid).json()
    assert result['state']=='passed' and result['can_handoff'],result


@pytest.mark.parametrize('first',[('red',),('green','red')])
def test_wrong_or_simultaneous_order_in_early_batch_is_latched(client,first):
    sid=start(client,'BATCH-WRONG-'+first[0],1).json()['id']
    result=batch(client,sid,[first]*3+[('green','red')]*3,list(range(0,600,100)),1.5)
    assert result.status_code==200,result.text
    assert result.json()['quarantined'],result.json()
    client.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'recorded-evidence'*100)})
    finished=client.post('/api/flow/finish/'+sid).json()
    assert finished['state']=='blocked' and not finished['can_handoff'],finished


@pytest.mark.parametrize('times',[[100,0],[0],[0,float('nan')],[0,8000000]])
def test_invalid_batch_timing_does_not_change_tracker(client,times):
    sid=start(client,'BATCH-INVALID-'+str(times),1).json()['id']
    result=batch(client,sid,[('green',)]*2,times,1)
    assert result.status_code==400,result.text
    assert production.active[sid]['tracker'].frames==0


def test_old_batch_cannot_rewrite_newer_evidence(client):
    sid=start(client,'BATCH-OLD',1).json()['id']
    assert batch(client,sid,[('green',)]*3,[0,100,200],1).status_code==200
    result=batch(client,sid,[('red',)]*3,[0,100,200],2)
    assert result.status_code==409
    assert production.active[sid]['tracker'].frames==3


@pytest.mark.parametrize('remove_cover',[False,True])
def test_final_frame_and_decision_are_atomic_after_recording_delay(client,remove_cover):
    c=client;sid=start(c,'ATOMIC-FINAL-'+str(remove_cover),1).json()['id']
    assert batch(c,sid,[('green',)]*3,[0,100,200],1).status_code==200
    assert batch(c,sid,[('green','red')]*3,[300,400,500],2).status_code==200
    assert c.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'recorded-evidence'*100)}).status_code==200
    # Model slow recording upload / a slow mobile round trip after the last batch.
    production.active[sid]['started']=time.monotonic()-8
    final=('green',) if remove_cover else ('green','red')
    response=c.post('/api/flow/finish/'+sid,files={'frame':('final.jpg',encoded(final),'image/jpeg')})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['state']=='passed',result


def test_recording_failure_reason_is_preserved_for_history(client):
    sid=start(client,'STOP-REASON',1).json()['id']
    response=client.post('/api/flow/abort/'+sid,params={'reason':'Wi-Fi disconnected'})
    assert response.status_code==200,response.text
    saved=client.get('/api/flow/attempts/'+sid).json()
    assert 'Wi-Fi disconnected' in saved['result']['error']


def test_recorded_assembly_keeps_order_when_delivered_one_batch_per_second(client):
    from calibration_profiles import comfortable_station_one
    from test_recorded_assembly import VIDEO, read_frame
    profile=comfortable_station_one(production.station_for(1))
    config=production.StationConfigIn(expected_version=profile['version'],anchor=profile['anchor'],steps=profile['steps'])
    assert client.put('/api/flow/stations/1/config',json=config.model_dump()).status_code==200
    sid=start(client,'RECORDED-WIFI-BATCH',1).json()['id']
    cap=cv2.VideoCapture(str(VIDEO))
    try:
        for second in range(10):
            files=[]
            for n in range(10):
                ok,data=cv2.imencode('.jpg',read_frame(cap,second+n/10));assert ok
                files.append(('frame',('image.jpg',data.tobytes(),'image/jpeg')))
            production.active[sid]['started']=time.monotonic()-(second+1.5)
            response=client.post('/api/flow/frame/'+sid,files=files,
                                 data={'captured_ms':json.dumps([second*1000+n*100 for n in range(10)])})
            assert response.status_code==200,response.text
            result=response.json()
            assert not result['quarantined'],result
        assert result['verified']==2,result
        assert [event['color'] for event in result['events']]==['green','red']
        assert client.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.mp4',VIDEO.read_bytes())}).status_code==200
        ok,data=cv2.imencode('.jpg',read_frame(cap,9.9));assert ok
        result=client.post('/api/flow/finish/'+sid,files={'frame':('final.jpg',data.tobytes(),'image/jpeg')}).json()
        assert result['state']=='passed' and result['can_handoff'],result
    finally:
        cap.release()
