"""Integration tests through real sessions and CSRF; isolated test DB only."""
from datetime import datetime,timedelta,timezone
import json
import pytest
import auth,db,production,workflows
from test_production_flow import client,start,finish,hold
PASSWORD='TestOnly-Password-739'

def login(c,name):
    c.cookies.clear()
    response=c.post('/api/auth/login',json={'username':name,'password':PASSWORD})
    assert response.status_code==200,response.text
    me=c.get('/api/auth/me').json()
    c.headers['X-CSRF-Token']=me['csrf_token']
    return me
def add(c,name,role):
    response=c.post('/api/users',json={'username':name,'display_name':name,'password':PASSWORD,'role':role})
    assert response.status_code==200,response.text
    return response.json()['id']

def test_authentication_csrf_and_session_revocation(client):
    c=client
    assert c.get('/api/auth/status').json()['configured']
    c.headers.pop('X-CSRF-Token')
    assert start(c,'NO-CSRF',1).status_code==403
    login(c,'fixtureadmin')
    uid=add(c,'operator1','operator')
    me=login(c,'operator1');saved_cookie=c.cookies.get(auth.COOKIE)
    assert c.post('/api/auth/logout').status_code==200
    c.cookies.set(auth.COOKIE,saved_cookie)
    assert c.get('/api/auth/me').status_code==401
    login(c,'fixtureadmin')
    assert c.patch('/api/users/'+str(me['id']),json={'enabled':False}).status_code==200
    c.cookies.clear()
    assert c.post('/api/auth/login',json={'username':'operator1','password':PASSWORD}).status_code==401
    for path in ('/api/flow/admin','/api/flow/admin/export','/media/secret.webm'):
        assert c.get(path).status_code==401
    with db.connect() as con:
        hashed=con.execute('SELECT password_hash FROM users WHERE id=?',(uid,)).fetchone()[0]
        assert PASSWORD not in hashed and auth.verify_password(PASSWORD,hashed)

def test_operator_cannot_spoof_identity_read_reports_or_other_attempts(client):
    c=client
    add(c,'operator1','operator');add(c,'operator2','operator')
    other=start(c,'ADMIN-WORK',1).json()['id']
    login(c,'operator1')
    response=start(c,'OWN-WORK',1);assert response.status_code==200,response.text
    own=response.json()['id']
    assert c.get('/api/flow/attempts/'+own).json()['operator']=='operator1'
    for path in ('/api/flow/admin','/api/flow/admin/export','/api/users','/api/reviews','/api/flow/attempts/'+other):
        assert c.get(path).status_code==403
    assert c.post('/api/flow/abort/'+other).status_code==403
    assert c.get('/api/flow/attempts/'+own).status_code==200
    assert c.get('/api/flow/my-history?station_id=1').json()['total']==1
    login(c,'operator2')
    assert c.get('/api/flow/attempts/'+own).status_code==403
    assert c.get('/api/flow/my-history?station_id=1').json()['total']==0

def test_first_setup_is_one_time_and_admin_cannot_disable_self(client):
    c=client;me=c.get('/api/auth/me').json()
    assert not auth.setup_path().exists()
    assert c.post('/api/auth/setup',json={'username':'secondadmin','display_name':'Admin','password':PASSWORD,'code':'wrong-code-long-enough-123'}).status_code==409
    assert c.patch('/api/users/'+str(me['id']),json={'enabled':False}).status_code==409

def test_supervisor_approval_preserves_failed_result_and_links_new_attempt(client):
    c=client
    add(c,'supervisor1','supervisor');add(c,'quality1','qc')
    sid=start(c,'REWORK-001',1).json()['id']
    assert c.post('/api/flow/abort/'+sid).status_code==200
    assert c.get('/api/reviews').json()[0]['attempt_id']==sid
    assert start(c,'REWORK-001',1).status_code==409
    login(c,'quality1')
    body={'decision':'rework_approved','reason':'ตรวจชิ้นงานแล้ว อนุญาตให้เริ่มตรวจใหม่'}
    assert c.post('/api/reviews/'+sid+'/decision',json=body).status_code==403
    assert start(c,'QC-CANNOT-START',1).status_code==403
    login(c,'supervisor1')
    assert c.post('/api/reviews/'+sid+'/decision',json={'decision':'rework_approved','reason':'          '}).status_code==400
    assert c.post('/api/reviews/'+sid+'/decision',json=body).status_code==200
    assert c.post('/api/reviews/'+sid+'/decision',json=body).status_code==409
    assert start(c,'SUPERVISOR-CANNOT-START',1).status_code==403
    login(c,'fixtureadmin')
    original=c.get('/api/flow/attempts/'+sid).json()
    assert original['state']=='interrupted' and original['ended_at']
    again=start(c,'REWORK-001',1);assert again.status_code==200,again.text
    new_id=again.json()['id'];assert new_id!=sid
    with db.connect() as con:
        assert con.execute('SELECT rework_of FROM flow_attempts WHERE id=?',(new_id,)).fetchone()[0]==sid
        row=con.execute('SELECT * FROM supervisor_reviews WHERE attempt_id=?',(sid,)).fetchone()
        assert row['reviewer_id'] is not None and row['reason']==body['reason']
    # Approval only permits a new inspection. It never unlocks station 2 itself.
    assert start(c,'REWORK-001',2).status_code==409
    passed=finish(c,new_id,[['green'],['green','red']])
    assert passed['state']=='passed'
    assert start(c,'REWORK-001',2).status_code==200

def test_test_rounds_reuse_external_qr_without_polluting_production(client):
    c=client
    real=start(c,'SAME-QR',1);assert real.status_code==200
    c.post('/api/flow/abort/'+real.json()['id'])
    run1=c.post('/api/test-runs',json={'label':'Round 1'}).json()['id']
    run2=c.post('/api/test-runs',json={'label':'Round 2'}).json()['id']
    def test_start(run,station=1):
        return c.post('/api/flow/start',json={'qr':'SAME-QR','station_id':station,'operator':'fixtureadmin','mime_type':'video/webm','test_mode':True,'test_run_id':run})
    one=test_start(run1);assert one.status_code==200,one.text
    first=one.json()
    assert first['source_qr']=='SAME-QR' and first['test_mode'] and first['qr']!='SAME-QR'
    assert test_start(run1,2).status_code==409
    c.post('/api/flow/abort/'+first['id'])
    assert test_start(run1).status_code==409
    two=test_start(run2);assert two.status_code==200,two.text
    assert two.json()['qr']!=first['qr']
    prod=c.get('/api/flow/admin').json()
    assert prod['total']==prod['stats']['total_attempts']==1
    test=c.get('/api/flow/admin?scope=test').json()
    assert test['total']==2 and test['filtered_stats']['total_attempts']==2
    assert test['stats']['total_attempts']==1
    assert c.get('/api/flow/admin?scope=all').json()['total']==3
    csv=c.get('/api/flow/admin/export?format=csv').content.decode('utf-8-sig')
    assert '__TEST__:' not in csv
    assert '__TEST__:' in c.get('/api/flow/admin/export?format=csv&scope=test').content.decode('utf-8-sig')
    assert c.post('/api/flow/lookup',json={'qr':'__TEST__:forged'}).status_code==400
    assert c.post('/api/flow/lookup',json={'qr':'SAME-QR','test_mode':True,'test_run_id':'missing'}).status_code==404

def test_watchdog_retains_evidence_and_never_passes_stale_work(client):
    c=client;sid=start(c,'DISCONNECTED-WORK',1).json()['id']
    hold(c,sid,['green'],3)
    before=c.get('/api/flow/attempts/'+sid).json()
    old=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
    with db.connect() as con:con.execute('UPDATE flow_attempts SET last_frame_at=?,updated_at=? WHERE id=?',(old,datetime.now(timezone.utc).isoformat(),sid))
    assert sid in workflows.expire_stale()
    assert sid not in production.active
    after=c.get('/api/flow/attempts/'+sid).json()
    assert after['state']=='interrupted' and after['ended_at']
    assert after['result']['evidence']==before['result']['evidence']
    assert any(a['event']=='connection_timeout' for a in after['audit'])
    assert c.get('/api/reviews').json()[0]['attempt_id']==sid
    assert start(c,'DISCONNECTED-WORK',2).status_code==409
    assert workflows.expire_stale()==[]
