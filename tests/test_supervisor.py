"""Supervisor permissions are enforced on the server, including direct API access."""
import pytest
import db
from test_production_flow import client, start
from test_access_workflows import add, login


@pytest.mark.parametrize('method,path',[
    ('get','/api/flow/admin'),('get','/api/flow/admin/export'),('get','/api/users'),
    ('get','/api/security-audit'),('get','/api/cameras'),('get','/api/cameras/events'),
    ('get','/api/cameras/not-a-camera/live'),('get','/api/reports'),
    ('get','/api/flow/my-history?station_id=1'),('get','/api/test-runs'),
    ('get','/api/worker/session'),('post','/api/flow/start'),('post','/api/cameras/open'),
    ('post','/api/test-runs'),('put','/api/steps'),('patch','/api/users/1'),
    ('get','/api/flow/stations'),('post','/api/qr/decode'),
])
def test_supervisor_is_denied_every_other_capability(client,method,path):
    add(client,'limitedhead','supervisor');login(client,'limitedhead')
    assert getattr(client,method)(path).status_code==403
    # Selecting station mode must not bypass the staff role restrictions.
    assert getattr(client,method)(path,headers={'X-Worker-Mode':'station'}).status_code==403


def test_supervisor_page_approval_and_preserved_history(client):
    c=client;add(c,'limitedhead','supervisor')
    sid=start(c,'HEAD-APPROVAL',1).json()['id'];c.post('/api/flow/abort/'+sid)
    login(c,'limitedhead')
    assert c.get('/supervisor').status_code==200
    for path in ('/admin','/access','/worker','/'):
        response=c.get(path,follow_redirects=False)
        assert response.status_code==303 and response.headers['location']=='/supervisor'
    assert c.get('/api/reviews').json()[0]['attempt_id']==sid
    url='/api/reviews/'+sid+'/decision'
    reason='ตรวจชิ้นงานแล้ว อนุญาตให้สแกนเพื่อตรวจซ้ำ'
    assert c.post(url,json={'decision':'rejected','reason':reason}).status_code==403
    assert c.post(url,json={'decision':'rework_approved','reason':reason},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert c.post(url,json={'decision':'rework_approved','reason':reason}).status_code==200
    assert c.post(url,json={'decision':'rework_approved','reason':reason}).status_code==409
    with db.connect() as conn:
        original=conn.execute('SELECT state,ended_at FROM flow_attempts WHERE id=?',(sid,)).fetchone()
        assert original['state']=='interrupted' and original['ended_at']
        assert conn.execute("SELECT count(*) FROM flow_audit WHERE attempt_id=? AND event='rework_approved'",(sid,)).fetchone()[0]==1
    login(c,'fixtureadmin')
    again=start(c,'HEAD-APPROVAL',1)
    assert again.status_code==200 and again.json()['id']!=sid
    assert start(c,'HEAD-APPROVAL',2).status_code==409


def test_supervisor_can_read_only_archived_videos(client):
    c=client;add(c,'limitedhead','supervisor')
    import production
    sid=start(c,'HEAD-VIDEO',1).json()['id']
    video=production.RECORDINGS/(sid+'.webm');video.write_bytes(b'test-video')
    c.post('/api/flow/abort/'+sid)
    url='/media/recordings/'+video.name
    with db.connect() as conn:conn.execute('UPDATE flow_attempts SET video_url=? WHERE id=?',(url,sid))
    login(c,'limitedhead')
    response=c.get('/api/supervisor/recordings?q=HEAD-VIDEO')
    assert response.status_code==200 and response.json()['total']==1
    assert response.json()['recordings'][0]['id']==sid
    assert response.json()['recordings'][0]['available']
    # File serving may be mounted outside this test's temporary recording dir;
    # authorization must allow this exact DB-backed URL, and deny other media.
    assert c.get(url).status_code!=403
    assert c.get('/media/evidence/secret.jpg').status_code==403
    assert c.get('/media/recordings/unregistered.webm').status_code==403
    assert c.get('/api/cameras/archive').status_code==200
    assert c.get('/api/supervisor/recordings?offset=0&limit=1').json()['limit']==1
    assert c.get('/api/supervisor/recordings?station_id=9').status_code==422


def test_operator_cannot_open_supervisor_portal(client):
    add(client,'limitedworker','operator');login(client,'limitedworker')
    assert client.get('/supervisor').status_code==403
    assert client.get('/api/supervisor/recordings').status_code==403
    assert client.post('/api/supervisor/qr/decode').status_code==403


def test_supervisor_decodes_real_qr_for_search_without_starting_work(client):
    import cv2
    import numpy as np
    c=client;add(c,'searchhead','supervisor');login(c,'searchhead')
    qr=cv2.QRCodeEncoder_create().encode('UI-RETRY-001')
    qr=cv2.copyMakeBorder(qr,4,4,4,4,cv2.BORDER_CONSTANT,value=255)
    qr=cv2.resize(qr,None,fx=8,fy=8,interpolation=cv2.INTER_NEAREST)
    ok,encoded=cv2.imencode('.png',qr);assert ok
    url='/api/supervisor/qr/decode'
    args={'files':{'frame':('qr.png',encoded.tobytes(),'image/png')}}
    assert c.post(url,**args).json()=={'qr':'UI-RETRY-001'}
    assert c.post(url,headers={'X-CSRF-Token':'wrong'},**args).status_code==403
    assert c.post(url,files={'frame':('bad',b'not-an-image')}).status_code==400
    assert c.post(url,files={'frame':('empty',b'')}).status_code==400
    assert c.post(url,files={'frame':('too-big',b'x'*3_000_001)}).status_code==413
    ok,empty=cv2.imencode('.png',np.full((120,120,3),255,dtype=np.uint8));assert ok
    assert c.post(url,files={'frame':('blank.png',empty.tobytes())}).json()=={'qr':None}
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM flow_attempts').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM camera_sessions').fetchone()[0]==0


def test_one_login_selects_permissions_from_account_with_separate_passwords(client):
    c=client
    supervisor_password='HeadOnly-Password-915'
    assert c.post('/api/users',json={'username':'separatehead','display_name':'Head',
        'password':supervisor_password,'role':'supervisor'}).status_code==200
    c.cookies.clear()
    assert c.get('/supervisor/login',follow_redirects=False).headers['location']=='/login'
    redirect=c.get('/supervisor',follow_redirects=False)
    assert redirect.status_code==303 and redirect.headers['location'].startswith('/login?')
    for username,password,portal in [
        ('separatehead','TestOnly-Password-739','supervisor'),
        ('fixtureadmin',supervisor_password,'admin')]:
        assert c.post('/api/auth/login',json={'username':username,'password':password,'portal':portal}).status_code==401
        assert c.get('/api/auth/me').status_code==401
    response=c.post('/api/auth/login',json={'username':'separatehead','password':supervisor_password,'portal':'supervisor'})
    assert response.status_code==200 and response.json()['role']=='supervisor'
    assert response.json()['home']=='/supervisor'
    assert c.get('/api/flow/admin').status_code==403
    c.cookies.clear()
    admin=c.post('/api/auth/login',json={'username':'fixtureadmin','password':'TestOnly-Password-739'})
    assert admin.status_code==200 and admin.json()['home']=='/admin'
    assert c.get('/api/flow/admin').status_code==200
