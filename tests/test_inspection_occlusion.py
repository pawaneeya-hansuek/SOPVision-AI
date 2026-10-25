"""Color-count inspection must recover when visible counts are restored."""
import cv2
import time
from test_fast_tracking import tracker, install_both, frame
from test_production_flow import client, start
import production
from pathlib import Path
from calibration_profiles import comfortable_station_one


def test_color_count_recovers_after_temporary_loss():
    tr=tracker();install_both(tr)
    hidden=frame('green',blocked=True)
    tr.feed(hidden,2.0);tr.feed(hidden,2.7)
    assert tr.snapshot()['steps'][1]['status']=='passed'
    noisy=hidden.copy();cv2.rectangle(noisy,(530,20),(550,40),(40,40,220),-1)
    tr.feed(noisy,2.8)
    assert not any(s['sequence_violation'] or s['ambiguous_sequence'] for s in tr.snapshot()['steps'])
    tr.feed(frame('green','red'),3.0)
    assert tr.snapshot(final=True)['status']=='pass', 'Completed colors stay confirmed'
    for n in range(1,13):tr.feed(frame('green','red'),3+n*.1)
    result=tr.snapshot(final=True)
    assert result['status']=='pass',result
    assert [event['color'] for event in result['events']]==['green','red']


def send(c,sid,img,second):
    ok,data=cv2.imencode('.jpg',img);assert ok
    production.active[sid]['started']=time.monotonic()-second
    response=c.post('/api/flow/frame/'+sid,files={'frame':('frame.jpg',data.tobytes(),'image/jpeg')})
    assert response.status_code==200,response.text
    return response.json()


def test_confirmed_base_hidden_by_hand_is_not_relabelled_as_reversed_order():
    tr=tracker()
    for n in range(11):tr.feed(frame('green'),n*.1)
    covered_base=frame('green','red')
    cv2.rectangle(covered_base,(75,110),(165,225),(180,180,180),-1)
    for n in range(12):tr.feed(covered_base,1.1+n*.1)
    result=tr.snapshot(final=True)
    assert result['status']=='pass'
    assert not any(s['sequence_violation'] or s['ambiguous_sequence'] for s in result['steps'])
    for n in range(13):tr.feed(frame('green','red'),2.4+n*.1)
    assert tr.snapshot(final=True)['status']=='pass'


def test_hand_occlusion_does_not_lock_valid_work_as_wrong_order(client):
    c=client;sid=start(c,'OCCLUSION-RECOVERY',1).json()['id']
    for start_at,img in [(0,frame('green')),(1.1,frame('green','red'))]:
        for n in range(11):result=send(c,sid,img,start_at+n*.1)
    assert result['verified']==2
    for n in range(10):result=send(c,sid,frame('green',blocked=True),2.2+n*.1)
    assert not result['quarantined']
    assert c.get('/api/flow/attempts/'+sid).json()['state']=='active'
    assert result['verified']==2
    for n in range(13):result=send(c,sid,frame('green','red'),3.3+n*.1)
    assert result['verified']==2 and not result['quarantined']
    assert c.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'video-bytes'*100)}).status_code==200
    result=c.post('/api/flow/finish/'+sid).json()
    assert result['state']=='passed' and result['can_handoff'],result


def test_occluded_final_image_preserves_completed_color_steps(client):
    c=client;sid=start(c,'OCCLUDED-FINAL',1).json()['id']
    for start_at,img in [(0,frame('green')),(1.1,frame('green','red'))]:
        for n in range(11):send(c,sid,img,start_at+n*.1)
    for n in range(10):send(c,sid,frame('green',blocked=True),2.2+n*.1)
    c.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'video-bytes'*100)})
    result=c.post('/api/flow/finish/'+sid).json()
    assert result['state']=='passed' and result['can_handoff']


def test_real_phone_capture_does_not_false_quarantine_and_recovers(client):
    c=client
    station=comfortable_station_one(production.station_for(1))
    config=production.StationConfigIn(expected_version=station['version'],anchor=station['anchor'],steps=station['steps'])
    assert c.put('/api/flow/stations/1/config',json=config.model_dump()).status_code==200
    sid=start(c,'PHONE-RECORDING-REGRESSION',1).json()['id']
    cap=cv2.VideoCapture(str(Path(__file__).parent/'fixtures/phone-inspection-occlusion.mp4'))
    n=0;maximum_verified=0
    try:
        while True:
            ok,img=cap.read()
            if not ok:break
            img=cv2.resize(img,(640,round(img.shape[0]*640/img.shape[1])))
            result=send(c,sid,img,n/6)
            assert not result['quarantined'],(n/6,result)
            assert result['verified']>=maximum_verified
            maximum_verified=result['verified']
            n+=1
    finally:cap.release()
    assert n==192 and maximum_verified==2
    assert result['verified']==2,result
    assert [e['color'] for e in result['events']]==['green','red']
    assert c.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'video-bytes'*100)}).status_code==200
    result=c.post('/api/flow/finish/'+sid).json()
    assert result['state']=='passed' and result['can_handoff'],result
