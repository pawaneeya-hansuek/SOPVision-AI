"""Faster valid assembly, with the same rejection of wrong/unsupported work."""
import copy
import cv2
import numpy as np
import pytest
from vision import Tracker
from calibration_profiles import comfortable_station_one
from production import STATIONS
from test_production_flow import client
import db,production,time

PROFILE=comfortable_station_one(STATIONS[0])
GREEN=(40,165,35)
RED=(35,45,220)

def image(base=True,cover=False,shift=(0,0),red_offset=(0,0),tiny=False,extra_red=False):
    frame=np.full((752,499,3),185,np.uint8)
    x,y=shift
    if base:cv2.rectangle(frame,(137+x,251+y),(355+x,589+y),GREEN,-1)
    if cover:
        dx,dy=red_offset
        width,height=(15,10) if tiny else (219,143)
        cv2.rectangle(frame,(137+x+dx,447+y+dy),(136+x+dx+width,446+y+dy+height),RED,-1)
    if extra_red:
        cv2.rectangle(frame,(390,120),(460,190),RED,-1)
    return frame

def tracker(profile=PROFILE):
    return Tracker(copy.deepcopy(profile['steps']),anchor=copy.deepcopy(profile['anchor']))

def hold(tr,frame,start,samples=7):
    for n in range(samples):tr.feed(frame,start+n*.1)

def correct(tr):
    hold(tr,image(),.01)
    hold(tr,image(cover=True),.71)
    return tr.snapshot(final=True)

def test_correct_overlapping_cover_passes_with_shorter_dwell_and_single_base_event():
    tr=tracker()
    result=correct(tr)
    assert result['status']=='pass',result
    assert result['verified']==2
    assert [e['color'] for e in result['events']]==['green','red']
    assert result['events'][0]['confirmed_at']<.8
    assert result['events'][1]['confirmed_at']-result['events'][0]['confirmed_at']<1

def test_small_position_variation_still_passes():
    tr=tracker()
    hold(tr,image(shift=(10,-8)),.01)
    hold(tr,image(cover=True,shift=(10,-8)),.71)
    assert tr.snapshot(final=True)['status']=='pass'

@pytest.mark.parametrize('mode',['missing_red','tiny_red'])
def test_wrong_or_incomplete_work_never_passes(mode):
    tr=tracker()
    hold(tr,image(),.01)
    hold(tr,image(cover=mode!='missing_red',tiny=mode=='tiny_red'),.71)
    assert tr.snapshot(final=True)['status']=='review',tr.snapshot(final=True)

def test_wrong_position_does_not_block_correct_order_and_counts():
    tr=tracker()
    hold(tr,image(shift=(80,100)),.01)
    hold(tr,image(shift=(80,100),cover=True,red_offset=(150,-300)),.71)
    assert tr.snapshot(final=True)['status']=='pass',tr.snapshot(final=True)

def test_extra_piece_of_a_color_does_not_pass():
    tr=tracker()
    hold(tr,image(),.01)
    hold(tr,image(cover=True,extra_red=True),.71)
    result=tr.snapshot(final=True)
    assert result['status']=='review',result
    assert result['steps'][1]['status']!='passed'

def test_two_frames_confirm_current_color_without_dwell():
    tr=tracker();tr.feed(image(),.01);tr.feed(image(),.51)
    assert tr.snapshot()['verified']==1

def test_completed_color_stays_confirmed_after_camera_moves_on():
    tr=tracker();assert correct(tr)['status']=='pass'
    hold(tr,image(),1.51)
    assert tr.snapshot(final=True)['status']=='pass'

def test_changed_position_still_passes_when_color_counts_match():
    tr=tracker();assert correct(tr)['status']=='pass'
    tr.feed(image(cover=True,shift=(27,0)),1.5)
    assert tr.snapshot(final=True)['status']=='pass'

@pytest.mark.parametrize('wrong_order,with_video,expected',[
    (False,True,'passed'),(False,False,'passed'),(True,True,'blocked')])
def test_real_handoff_checks_color_counts_without_requiring_recording(client,wrong_order,with_video,expected):
    station=comfortable_station_one(production.station_for(1))
    body=production.StationConfigIn(expected_version=station['version'],anchor=station['anchor'],steps=station['steps'])
    saved=client.put('/api/flow/stations/1/config',json=body.model_dump())
    assert saved.status_code==200,saved.text
    response=client.post('/api/flow/start',json={'qr':'COMFORTABLE-FLOW','station_id':1,'operator':'TEST','mime_type':'video/webm'})
    assert response.status_code==200,response.text
    sid=response.json()['id']
    first=image(base=False,cover=True) if wrong_order else image()
    for start,frame in ((.01,first),(.71,image(cover=True))):
        ok,encoded=cv2.imencode('.jpg',frame);assert ok
        for n in range(7):
            production.active[sid]['started']=time.monotonic()-(start+n*.1)
            result=client.post('/api/flow/frame/'+sid,files={'frame':('frame.jpg',encoded.tobytes(),'image/jpeg')})
            assert result.status_code==200,result.text
    if with_video:
        response=client.post('/api/flow/recording/'+sid+'/0',files={'chunk':('recording.webm',b'recording-test-bytes'*100,'video/webm')})
        assert response.status_code==200,response.text
    done=client.post('/api/flow/finish/'+sid)
    assert done.status_code==200,done.text
    data=done.json()
    assert data['state']==expected,data
    assert data['can_handoff']==(expected=='passed')
    assert data['job']['stations'][1]['state']==('ready' if expected=='passed' else 'locked')
