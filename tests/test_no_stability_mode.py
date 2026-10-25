"""Fast mode records each color on its first ordered observation."""
import cv2
import numpy as np
from vision import Tracker
from test_fast_tracking import STEPS, ANCHOR, frame
from test_production_flow import client, start
from test_inspection_occlusion import send


def moving(colors,offset,bright):
    image=frame(*colors)
    gray=(image[:,:,0]==90)&(image[:,:,1]==90)&(image[:,:,2]==90)
    image[gray]=bright
    return cv2.warpAffine(image,np.float32([[1,0,offset],[0,1,offset]]),(640,480),
                         borderValue=(bright,bright,bright))


def test_two_moving_frames_confirm_each_step_without_waiting():
    tr=Tracker(STEPS,anchor=ANCHOR,require_stability=False)
    for n,colors in enumerate([('green',),('green',),('green','red'),('green','red')]):
        found,_=tr.feed(moving(colors,0 if n%2==0 else 16,90 if n%2==0 else 140),n*.1)
    result=tr.snapshot(final=True)
    assert result['status']=='pass' and result['inspection_mode']=='fast',result
    assert [event['confirmed_at'] for event in result['events']]==[0,.2]
    assert all('นิ่ง' not in s['reason'] for s in result['steps'])


def test_fast_mode_requires_ordered_colors_and_exact_counts():
    for colors in [('red',),('green','red')]:
        tr=Tracker(STEPS,anchor=ANCHOR,require_stability=False)
        tr.feed(frame(*colors),0);tr.feed(frame(*colors),.1)
        assert tr.snapshot(final=True)['status']=='review'
    tr=Tracker(STEPS,anchor=ANCHOR,require_stability=False)
    for n,colors in enumerate([('green',),('green',),('green','red'),('green','red')]):
        tr.feed(frame(*colors),n*.1)
    assert tr.snapshot(final=True)['status']=='pass'
    tr.feed(frame('green'),.4)
    assert tr.snapshot(final=True)['status']=='pass'


def test_actual_worker_uses_fast_mode_and_confirms_while_moving(client):
    c=client;response=start(c,'FAST-NO-STILLNESS',1);assert response.status_code==200
    sid=response.json()['id']
    assert response.json()['station']['require_stability'] is False
    for n,colors in enumerate([('green',),('green',),('green','red'),('green','red')]):
        result=send(c,sid,moving(colors,0 if n%2==0 else 16,90 if n%2==0 else 140),n*.1)
    assert result['verified']==2 and not result['quarantined'],result
    assert result['inspection_mode']=='fast'
    assert c.post('/api/flow/recording/'+sid+'/0',files={'chunk':('clip.webm',b'video-bytes'*100)}).status_code==200
    done=c.post('/api/flow/finish/'+sid).json()
    assert done['state']=='passed' and done['can_handoff'],done
