"""A completed orange step must not block a correctly detected purple step."""
from pathlib import Path
import cv2
from vision import Tracker,detect_colors
from test_fast_tracking import frame,COLORS
from test_production_flow import client,start,finish
from test_prior_station_check import first_station,send

STEPS=[{'id':301,'name':'orange','color':'orange'},
       {'id':302,'name':'purple','color':'purple'}]
SCREENSHOT=Path(__file__).parent/'fixtures/station3-purple-visible.png'


def test_actual_screenshot_confirms_purple_even_with_two_orange_regions():
    tracker=Tracker(STEPS)
    tracker.feed(frame('orange'),0)
    assert tracker.snapshot()['verified']==1
    screenshot=cv2.imread(str(SCREENSHOT));assert screenshot is not None
    found=detect_colors(screenshot,STEPS)
    assert found['orange']['count']==2 and found['purple']['count']==1
    tracker.feed(screenshot,.08)
    result=tracker.snapshot(final=True)
    assert result['status']=='pass' and result['verified']==2,result
    assert result['events'][-1]['confirmed_at']==.08


def test_excess_current_or_unconfirmed_color_is_still_rejected():
    two_orange=frame('orange')
    cv2.rectangle(two_orange,(430,330),(495,395),COLORS['orange'],-1)
    tracker=Tracker(STEPS);tracker.feed(two_orange,0)
    assert tracker.snapshot()['verified']==0
    tracker=Tracker(STEPS);tracker.feed(frame('orange'),0)
    two_purple=frame('orange','purple')
    cv2.rectangle(two_purple,(430,330),(495,395),COLORS['purple'],-1)
    tracker.feed(two_purple,.08)
    assert tracker.snapshot()['verified']==1


def test_actual_screenshot_auto_completes_station_three_with_prior_check(client):
    qr='PURPLE-SCREENSHOT-REGRESSION';first_station(client,qr)
    second=start(client,qr,2).json()['id']
    assert finish(client,second,[['blue'],['blue','yellow']])['state']=='passed'
    response=client.post('/api/flow/start',json={'qr':qr,'station_id':3,'operator':'TEST','auto_complete':True})
    assert response.status_code==200,response.text
    sid=response.json()['id']
    first=send(client,sid,'green','red','blue','yellow','orange')
    assert first['verified']==1 and first['prior_check']['passed']
    response=client.post('/api/flow/frame/'+sid,files={'frame':('camera.png',SCREENSHOT.read_bytes(),'image/png')})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['visible']['orange']['count']==2 and result['visible']['purple']['count']==1
    assert result['completion']['state']=='passed' and result['completion']['can_handoff']
