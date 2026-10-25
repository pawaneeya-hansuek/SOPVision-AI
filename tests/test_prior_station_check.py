"""A later station must see the accepted earlier colors on the same QR piece."""
import json
import time
import cv2
import db
import production
from test_production_flow import client,start,finish
from test_fast_tracking import frame,COLORS


def image(*colors):
    output=frame()
    for n,color in enumerate(colors):
        cv2.rectangle(output,(20+n*90,140),(85+n*90,205),COLORS[color],-1)
    ok,raw=cv2.imencode('.jpg',output);assert ok
    return raw.tobytes()


def send(c,sid,*colors):
    response=c.post('/api/flow/frame/'+sid,files={'frame':('camera.jpg',image(*colors),'image/jpeg')})
    assert response.status_code==200,response.text
    return response.json()


def first_station(c,qr):
    sid=start(c,qr,1).json()['id']
    assert finish(c,sid,[['green'],['green','red']])['state']=='passed'
    return sid


def test_station_two_checks_previous_colors_before_confirming_new_steps(client):
    qr='PRIOR-PHYSICAL-CHECK';previous=first_station(client,qr)
    response=start(client,qr,2);assert response.status_code==200,response.text
    sid=response.json()['id']
    assert {s['source_attempt_id'] for s in response.json()['station']['prior_steps']}=={previous}
    result=send(client,sid,'blue')
    assert result['verified']==0 and not result['prior_check']['passed']
    assert {s['color'] for s in result['prior_check']['steps'] if s['status']=='missing'}=={'green','red'}
    result=send(client,sid,'green','blue')
    assert result['verified']==0 and result['prior_check']['verified']==1
    # Old colors are an unordered incoming check, not another assembly sequence.
    result=send(client,sid,'green','red','blue')
    assert result['prior_check']['passed'] and result['verified']==1
    assert result['evidence']['handoff'].endswith('_handoff.jpg')
    assert (production.EVIDENCE/(f'flow_{sid}_handoff.jpg')).exists()
    result=send(client,sid,'yellow')
    assert result['verified']==2 and result['prior_check']['passed']
    assert client.post('/api/flow/finish/'+sid).json()['state']=='passed'


def test_missing_prior_colors_prevent_pass_even_when_all_new_colors_seen(client):
    qr='PRIOR-MISSING';first_station(client,qr)
    sid=start(client,qr,2).json()['id']
    send(client,sid,'blue');send(client,sid,'blue','yellow')
    result=client.post('/api/flow/finish/'+sid).json()
    assert result['state']=='blocked' and not result['can_handoff']
    assert not result['inspection']['prior_check']['passed']
    assert start(client,qr,3).status_code==409


def test_station_three_requires_colors_from_all_earlier_stations(client):
    qr='CUMULATIVE-COLORS';first_station(client,qr)
    sid=start(client,qr,2).json()['id']
    assert finish(client,sid,[['blue'],['blue','yellow']])['state']=='passed'
    response=start(client,qr,3);assert response.status_code==200,response.text
    sid=response.json()['id']
    assert {s['color'] for s in response.json()['station']['prior_steps']}=={'green','red','blue','yellow'}
    result=send(client,sid,'blue','yellow','orange')
    assert result['verified']==0 and not result['prior_check']['passed']
    result=send(client,sid,'green','red','blue','yellow','orange')
    assert result['verified']==1 and result['prior_check']['verified']==4
    result=send(client,sid,'purple')
    assert result['verified']==2
    completed=client.post('/api/flow/finish/'+sid).json()
    assert completed['state']=='passed' and completed['job']['completed']


def test_prior_check_does_not_delay_last_color_auto_completion(client):
    qr='FAST-PRIOR-CHECK';first_station(client,qr)
    response=client.post('/api/flow/start',json={'qr':qr,'station_id':2,'operator':'TEST','auto_complete':True})
    assert response.status_code==200,response.text
    sid=response.json()['id']
    assert send(client,sid,'green','red','blue')['verified']==1
    result=send(client,sid,'yellow')
    assert result['completion']['state']=='passed' and result['completion']['can_handoff']
    saved=client.get('/api/flow/attempts/'+sid).json()
    assert saved['result']['prior_check']['passed'] and saved['result']['frames']==2


def test_incomplete_previous_evidence_cannot_be_used_for_handoff(client):
    qr='CORRUPT-PREVIOUS';previous=first_station(client,qr)
    with db.connect() as c:
        row=c.execute('SELECT result_json FROM flow_attempts WHERE id=?',(previous,)).fetchone()
        result=json.loads(row['result_json']);result['events']=result['events'][:1]
        c.execute('UPDATE flow_attempts SET result_json=? WHERE id=?',(json.dumps(result),previous))
    response=start(client,qr,2)
    assert response.status_code==409


def test_another_qr_cannot_borrow_a_previous_station_pass(client):
    first_station(client,'PREVIOUS-OTHER-QR')
    assert start(client,'UNPROCESSED-QR',2).status_code==409
