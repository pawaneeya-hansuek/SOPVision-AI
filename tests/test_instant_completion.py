"""The last color commits pass before video upload or any final camera request."""
import json
import time
import db
import production
import workflows
from test_production_flow import client
from test_frame_batches import batch
from test_station_access import enter


def begin(c,qr):
    response=c.post('/api/flow/start',json={'qr':qr,'station_id':1,'operator':'TEST',
        'mime_type':'video/webm','auto_complete':True})
    assert response.status_code==200,response.text
    return response.json()['id']


def complete(c,sid):
    assert batch(c,sid,[('green',)],[0],.1).json()['verified']==1
    response=batch(c,sid,[('red',)],[80],.2)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['verified']==2 and result['completion']['state']=='passed'
    assert result['completion']['can_handoff']
    return result


def test_last_color_commits_pass_without_video_or_final_frame(client):
    c=client;c.cookies.clear();enter(c)
    sid=begin(c,'LAST-COLOR-COMMITS')
    complete(c,sid)
    saved=c.get('/api/flow/attempts/'+sid).json()
    assert saved['state']=='passed' and saved['ended_at']
    assert saved['recorded_chunks']==0 and saved['result']['recording_pending']
    assert saved['result']['frames']==2
    # Another station can start even while the first station's video is pending.
    assert c.post('/api/flow/start',json={'qr':'LAST-COLOR-COMMITS','station_id':2,'operator':'TEST'}).status_code==200
    # A different QR at the same station is also immediately ready.
    begin(c,'NEXT-WORK-WHILE-VIDEO-PENDING')


def test_background_video_appends_in_order_and_never_changes_pass(client):
    c=client;sid=begin(c,'BACKGROUND-ARCHIVE')
    complete(c,sid)
    for sequence in range(2):
        response=c.post(f'/api/flow/recording/{sid}/{sequence}',files={'chunk':('clip.webm',b'evidence'*100)})
        assert response.status_code==200,response.text
    duplicate=c.post(f'/api/flow/recording/{sid}/1',files={'chunk':('clip.webm',b'evidence'*100)})
    assert duplicate.status_code==200 and duplicate.json()['duplicate']
    saved=c.get('/api/flow/attempts/'+sid).json()
    assert saved['state']=='passed' and saved['recorded_bytes']==1600 and saved['video_url']
    response=c.post('/api/flow/finish/'+sid)
    assert response.status_code==200,response.text
    assert not response.json()['inspection']['recording_pending']
    assert sid not in production.active
    assert c.post('/api/flow/finish/'+sid).json()['state']=='passed'
    assert c.post('/api/flow/abort/'+sid).json()['state']=='passed'


def test_incomplete_or_wrong_order_work_cannot_auto_complete(client):
    sid=begin(client,'AUTO-INCOMPLETE')
    result=batch(client,sid,[('green',)],[0],.1).json()
    assert 'completion' not in result
    assert client.get('/api/flow/attempts/'+sid).json()['state']=='active'
    wrong=begin(client,'AUTO-WRONG-ORDER')
    result=batch(client,wrong,[('red',),('red',),('green','red')],[0,80,160],.3).json()
    assert result['quarantined'] and 'completion' not in result


def test_lost_archive_does_not_revoke_pass_and_frees_memory(client):
    sid=begin(client,'ARCHIVE-LOST')
    complete(client,sid)
    with db.connect() as c:
        c.execute("UPDATE flow_attempts SET updated_at=datetime('now','-11 minutes') WHERE id=?",(sid,))
    workflows.expire_stale()
    saved=client.get('/api/flow/attempts/'+sid).json()
    assert saved['state']=='passed' and not saved['result']['recording_pending']
    assert saved['result']['recording_error'] and sid not in production.active
