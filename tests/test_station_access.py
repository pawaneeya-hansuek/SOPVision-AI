"""Password-free station entry with server-enforced scope and CSRF."""
import auth,station_access
from test_production_flow import client,start,finish

def enter(c):
    response=c.get('/api/worker/session')
    assert response.status_code==200,response.text
    actor=response.json()
    assert actor['guest'] and actor['role']=='operator' and actor['id']<0
    c.headers['X-CSRF-Token']=actor['csrf_token']
    c.headers['X-Worker-Mode']='station'
    return actor

def test_worker_page_needs_no_login_but_staff_data_stays_protected(client):
    c=client;c.cookies.clear();c.headers.clear()
    assert c.get('/worker').status_code==200
    for path in ('/api/flow/admin','/api/flow/admin/export','/api/users','/api/reviews'):
        assert c.get(path).status_code==401
    actor=enter(c)
    page=c.get('/admin',follow_redirects=False)
    assert page.status_code==303 and page.headers['location'].startswith('/login')
    assert c.get('/api/worker/session').json()['id']==actor['id']
    for path in ('/api/flow/admin','/api/flow/admin/export','/api/users','/api/reviews'):
        assert c.get(path).status_code==403
    assert c.get('/api/flow/stations').status_code==200
    c.headers.pop('X-CSRF-Token')
    assert start(c,'NO-STATION-CSRF',1).status_code==403
    enter(c)
    run=c.post('/api/test-runs',json={'label':'Station guest test'})
    assert run.status_code==200,run.text
    assert c.get('/api/auth/me').status_code==403
    assert c.post('/api/auth/logout').status_code==403

def test_guest_station_handoff_requires_real_pass_and_forces_station_identity(client):
    c=client;c.cookies.clear();actor=enter(c)
    assert start(c,'GUEST-HANDOFF',2).status_code==409
    started=start(c,'GUEST-HANDOFF',1)
    assert started.status_code==200,started.text
    sid=started.json()['id']
    saved=c.get('/api/flow/attempts/'+sid).json()
    assert saved['operator']==station_access.operator_for(actor,1)
    passed=finish(c,sid,[['green'],['green','red']])
    assert passed['state']=='passed'
    # A second station/browser can continue the same piece without a user account.
    c.cookies.clear();second=enter(c)
    assert second['id']!=actor['id']
    assert c.get('/api/flow/attempts/'+sid).status_code==403
    next_attempt=start(c,'GUEST-HANDOFF',2)
    assert next_attempt.status_code==200,next_attempt.text
    assert c.get('/api/flow/my-history?station_id=1').json()['total']==0
    assert c.get('/api/flow/my-history?station_id=2').json()['total']==1
    c.post('/api/flow/abort/'+next_attempt.json()['id'])
    assert start(c,'GUEST-HANDOFF',3).status_code==409

def test_guest_owns_only_its_attempts_camera_and_unload_abort(client):
    c=client;c.cookies.clear();actor=enter(c)
    sid=start(c,'OWN-GUEST-WORK',1).json()['id']
    worker_cookie=c.cookies.get(station_access.COOKIE)
    body={'id':'guest-camera-123456','token':'camera-token-long-enough-123456789',
          'source':'worker','station_id':1,'operator':'FORGED','device_label':'Station camera','mime_type':'video/webm'}
    opened=c.post('/api/cameras/open',json=body)
    assert opened.status_code==200,opened.text
    c.cookies.clear();enter(c)
    assert c.get('/api/flow/attempts/'+sid).status_code==403
    assert c.post('/api/flow/abort/'+sid).status_code==403
    assert c.get('/api/cameras/guest-camera-123456/live').status_code==403
    assert c.get('/media/evidence/'+sid+'.jpg').status_code==403
    c.cookies.clear();c.cookies.set(station_access.COOKIE,worker_cookie)
    c.headers.clear()
    # Real sendBeacon requests carry the station mode and CSRF in their JSON body.
    result=c.post('/api/flow/abort/'+sid,json={'csrf':actor['csrf_token'],'worker_mode':'station'})
    assert result.status_code==200,result.text
    assert result.json()['state']=='interrupted'
    close=c.post('/api/cameras/guest-camera-123456/close',json={'token':body['token'],'csrf':actor['csrf_token'],'worker_mode':'station'})
    assert close.status_code==200,close.text

def test_guest_mode_does_not_replace_admin_identity_on_staff_pages(client):
    c=client;admin_csrf=c.headers['X-CSRF-Token']
    original=c.get('/api/auth/me').json()
    guest=enter(c)
    assert c.get('/api/flow/admin').status_code==403
    assert c.post('/api/users',json={'username':'forged','display_name':'forged','password':'never-create-this','role':'admin'}).status_code==403
    c.headers.pop('X-Worker-Mode');c.headers['X-CSRF-Token']=admin_csrf
    assert c.get('/api/auth/me').json()['id']==original['id']
    assert c.get('/api/flow/admin').status_code==200
    assert c.get('/api/users').status_code==200
