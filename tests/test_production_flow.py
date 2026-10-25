"""Behavioral server tests for QR handoff; no real camera needed."""
import io
import sqlite3
from pathlib import Path

import cv2
import pytest
import time
from fastapi import HTTPException
from fastapi.testclient import TestClient

import db
import production
import main
import gemini_review
from main import app
from test_fast_tracking import frame as vision_frame, COLORS


@pytest.fixture
def client(tmp_path, monkeypatch):
    import playback
    monkeypatch.setattr(playback,'CACHE',tmp_path/'playback')
    monkeypatch.setattr(db, 'DB', tmp_path / 'test.db')
    record_dir = tmp_path / 'recordings'
    evidence_dir = tmp_path / 'evidence'
    record_dir.mkdir()
    evidence_dir.mkdir()
    monkeypatch.setattr(production, 'RECORDINGS', record_dir)
    monkeypatch.setattr(production, 'EVIDENCE', evidence_dir)
    production.active.clear()
    with TestClient(app) as c:
        from auth_helpers import bootstrap
        bootstrap(c)
        yield c
    production.active.clear()


def frame(colors):
    ok, buf = cv2.imencode('.jpg', vision_frame(*colors))
    assert ok
    return buf.tobytes()


def start(client, qr, station):
    return client.post('/api/flow/start', json={'qr': qr, 'station_id': station,
         'operator': f'EMP-{station}', 'mime_type': 'video/webm'})


def feed(client, sid, colors):
    sess = production.active[sid]
    colors = list(colors)
    raw=frame(colors)
    if sess['station']['id'] > 1:
        colors=list(dict.fromkeys([step['color'] for step in sess['station']['prior_steps']]+colors))
        image=vision_frame()
        for n,color in enumerate(colors):
            cv2.rectangle(image,(20+n*90,140),(85+n*90,205),COLORS[color],-1)
        ok,encoded=cv2.imencode('.jpg',image);assert ok
        raw=encoded.tobytes()
    elapsed = sess.get('test_elapsed', 0.0)
    sess['started'] = time.monotonic() - elapsed
    response = client.post(f'/api/flow/frame/{sid}',
            files={'frame': ('image.jpg', raw, 'image/jpeg')})
    sess['test_elapsed'] = elapsed + 0.1
    return response


def hold(client, sid, colors, samples=10):
    response = None
    for _ in range(samples):
        response = feed(client, sid, colors)
        assert response.status_code == 200, response.text
    return response


def finish(client, sid, steps, with_video=True):
    for colors in steps:
        hold(client, sid, colors)
    if with_video:
        up = client.post(f'/api/flow/recording/{sid}/0',
                files={'chunk': ('recording.webm', bytes(range(256)) * 8, 'video/webm')})
        assert up.status_code == 200, up.text
    response = client.post(f'/api/flow/finish/{sid}')
    assert response.status_code == 200, response.text
    return response.json()


def test_qr_handoff_prevents_skip_and_quarantines_failed_job(client):
    qr = 'existing-factory-qr://WO-2026-009'
    status = client.post('/api/flow/lookup', json={'qr': qr}).json()
    assert [s['state'] for s in status['stations']] == ['ready', 'locked', 'locked']
    assert start(client, qr, 2).status_code == 409
    station1 = start(client, qr, 1)
    assert station1.status_code == 200, station1.text
    sid = station1.json()['id']
    assert start(client, qr, 2).status_code == 409
    failed = finish(client, sid, [['red']])
    assert failed['state'] == 'blocked'
    assert not failed['can_handoff']
    assert [s['state'] for s in failed['job']['stations']] == ['blocked', 'locked', 'locked']
    assert start(client, qr, 2).status_code == 409
    retried = start(client, qr, 1)
    assert retried.status_code == 409
    assert failed['job']['quarantined']
    # The next physical workpiece can start immediately at this station.
    qr = 'NEXT-WORKPIECE'
    next_piece = start(client, qr, 1)
    assert next_piece.status_code == 200
    passed = finish(client, next_piece.json()['id'], [['green'], ['green', 'red']])
    assert passed['state'] == 'passed'
    assert [s['state'] for s in passed['job']['stations']] == ['passed', 'ready', 'locked']
    assert start(client, qr, 1).status_code == 409  # cannot replace accepted record
    s2 = start(client, qr, 2)
    assert s2.status_code == 200
    p2 = finish(client, s2.json()['id'], [['blue'], ['blue', 'yellow']])
    assert p2['state'] == 'passed'
    assert [s['state'] for s in p2['job']['stations']] == ['passed', 'passed', 'ready']
    s3 = start(client, qr, 3)
    assert s3.status_code == 200
    p3 = finish(client, s3.json()['id'], [['orange'], ['orange', 'purple']])
    assert p3['state'] == 'passed'
    assert p3['job']['completed']
    assert all(s['state'] == 'passed' for s in p3['job']['stations'])
    admin = client.get('/api/flow/admin').json()['stats']
    assert admin['total_jobs'] == 2
    assert admin['completed_jobs'] == 1
    assert admin['passed'] == 3
    assert start(client, qr, 3).status_code == 409
    details = client.get(f'/api/flow/attempts/{s3.json()["id"]}').json()
    assert details['result']['verified'] == 2
    assert details['video_url'].startswith('/media/recordings/')
    assert details['frame_url'].endswith(f'flow_final_{s3.json()["id"]}.jpg')
    assert details['result']['evidence']['final'] == details['frame_url']
    assert cv2.imread(str(production.EVIDENCE / Path(details['frame_url']).name)) is not None


def test_missing_video_does_not_block_complete_color_inspection(client):
    qr = 'ABC123'
    response = client.post('/api/flow/start', json={
        'qr': qr, 'station_id': 1, 'operator': 'EMP-1'})
    assert response.status_code == 200, response.text
    sid = response.json()['id']
    result = finish(client, sid, [['green'], ['green', 'red']], with_video=False)
    assert result['state'] == 'passed'
    assert result['can_handoff']
    assert result['inspection']['recording_error']
    assert result['frame_url']
    assert cv2.imread(str(production.EVIDENCE / Path(result['frame_url']).name)) is not None
    assert client.post('/api/flow/lookup', json={'qr': qr}).json()['stations'][1]['state'] == 'ready'


def test_sop_accepts_only_step_name_and_color(client):
    response = client.put('/api/steps', json={'steps': [
        {'name': 'ฐาน', 'color': 'green'},
        {'name': 'ฝาครอบ', 'color': 'red'},
    ]})
    assert response.status_code == 200, response.text
    assert [(step['name'], step['color']) for step in response.json()] == [
        ('ฐาน', 'green'), ('ฝาครอบ', 'red')]
    assert all(step['min_pct'] == 0.5 for step in response.json())


def test_one_installed_part_cannot_pass_station_or_unlock_next(client):
    qr = 'ONLY-ONE-PART'
    sid = start(client, qr, 1).json()['id']
    result = finish(client, sid, [['green']])
    assert result['state'] == 'blocked'
    assert not result['can_handoff']
    assert result['inspection']['verified'] == 1
    assert result['inspection']['total'] == 2
    assert result['inspection']['completion_error']
    assert [step['status'] for step in result['inspection']['steps']] != ['passed', 'passed']
    assert start(client, qr, 2).status_code == 409


def test_incomplete_saved_station_sop_is_rejected_closed(monkeypatch):
    station = production.STATIONS[0]
    monkeypatch.setattr(db, 'load_station_config', lambda _: {
        'version': 1, 'anchor': station['anchor'], 'steps': station['steps'][:1],
    })
    with pytest.raises(HTTPException) as error:
        production.station_for(station['id'])
    assert error.value.status_code == 500
    assert 'ไม่ครบ' in error.value.detail


def test_completed_color_sequence_survives_camera_moving_to_next_qr(client):
    qr = 'PART-REMOVED'
    sid = start(client, qr, 1).json()['id']
    hold(client, sid, ['green'])
    hold(client, sid, ['green', 'red'])
    hold(client, sid, ['green'])
    client.post(f'/api/flow/recording/{sid}/0',
                files={'chunk': ('recording.webm', b'x' * 500, 'video/webm')})
    result = client.post(f'/api/flow/finish/{sid}').json()
    assert result['state'] == 'passed'
    assert result['inspection']['steps'][1]['status'] == 'passed'
    assert result['inspection']['steps'][1]['reason']
    assert cv2.imread(str(production.EVIDENCE / Path(result['frame_url']).name)) is not None
    assert start(client, qr, 2).status_code == 200


def test_aborted_attempt_saves_annotated_frame_and_step_reasons(client):
    sid = start(client, 'ABORT-EVIDENCE', 1).json()['id']
    hold(client, sid, ['green'])
    result = client.post(f'/api/flow/abort/{sid}').json()
    assert result['state'] == 'interrupted'
    assert result['frame_url'].endswith(f'flow_final_{sid}.jpg')
    assert result['inspection']['steps'][1]['reason']
    assert cv2.imread(str(production.EVIDENCE / Path(result['frame_url']).name)) is not None


def test_gemini_review_for_qr_attempt_is_advisory_and_uses_saved_evidence(client, monkeypatch):
    sid = start(client, 'GEMINI-QR-REVIEW', 1).json()['id']
    hold(client, sid, ['green'])
    before = client.get(f'/api/flow/attempts/{sid}').json()['result']
    calls = []

    def fake_review(prompt, image_paths):
        calls.append((prompt, image_paths))
        return {'text': 'พบชิ้นส่วนสีเขียว ควรตรวจขั้นตอนถัดไป',
                'note': 'AI เป็นผู้ช่วยตีความภาพ ไม่ใช่การยืนยันผลตรวจขั้นตอน'}

    monkeypatch.setattr(production, 'review_images', fake_review)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    response = client.post(f'/api/flow/attempts/{sid}/ai-review')
    assert response.status_code == 200
    assert response.json()['text'].startswith('พบชิ้นส่วน')
    assert calls and calls[0][1]
    assert all(path.is_file() for path in calls[0][1])
    assert 'เทียบกับขั้นตอน' in calls[0][0]
    after = client.get(f'/api/flow/attempts/{sid}').json()['result']
    assert after == before


def test_gemini_review_for_standard_report(client, monkeypatch):
    image_path = production.EVIDENCE / 'report-review.jpg'
    assert cv2.imwrite(str(image_path), vision_frame('green'))
    db.save_report('GEMINI-REPORT-REVIEW', 'upload', '2026-01-01T00:00:00+00:00',
                   {'elapsed': 1, 'status': 'review', 'verified': 0, 'total': 2,
                    'issues': 2, 'steps': [], 'events': [],
                    'evidence': {'green': '/media/evidence/report-review.jpg'}})
    monkeypatch.setattr(main, 'review_images', lambda prompt, paths: {
        'text': 'แนะนำตรวจภาพเพิ่มเติม', 'note': 'AI เป็นผู้ช่วยเท่านั้น'})
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    response = client.post('/api/reports/GEMINI-REPORT-REVIEW/ai-review')
    assert response.status_code == 200
    assert response.json()['text'] == 'แนะนำตรวจภาพเพิ่มเติม'


def test_gemini_review_reports_missing_server_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(ValueError, match='GEMINI_API_KEY'):
        gemini_review.review_images('review', [])


def test_station_config_is_versioned_and_attempt_keeps_its_snapshot(client):
    station = client.get('/api/flow/stations').json()[0]
    config = {'anchor': station['anchor'], 'steps': station['steps']}
    first = client.put('/api/flow/stations/1/config',
                       json={'expected_version': 0, **config})
    assert first.status_code == 200, first.text
    assert first.json()['version'] == 1
    sid = start(client, 'ROI-SNAPSHOT', 1).json()['id']
    snapshot = client.get(f'/api/flow/attempts/{sid}').json()['station']
    assert snapshot['version'] == 1
    assert snapshot['steps'][1]['roi'] == config['steps'][1]['roi']
    assert client.put('/api/flow/stations/1/config',
                      json={'expected_version': 0, **config}).status_code == 409
    assert client.put('/api/flow/stations/1/config',
                      json={'expected_version': 1, **config}).status_code == 409
    client.post(f'/api/flow/abort/{sid}')
    config['steps'][1]['roi']['x'] = .17
    second = client.put('/api/flow/stations/1/config',
                        json={'expected_version': 1, **config})
    assert second.status_code == 200, second.text
    assert second.json()['version'] == 2
    assert client.get(f'/api/flow/attempts/{sid}').json()['station']['version'] == 1


def test_existing_database_is_backed_up_before_station_config_migration(tmp_path, monkeypatch):
    path = tmp_path / 'existing.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE flow_jobs (qr TEXT PRIMARY KEY, created_at TEXT)')
        conn.execute("INSERT INTO flow_jobs VALUES ('KEEP-ME', '2026-01-01')")
    monkeypatch.setattr(db, 'DB', path)
    db.initialize()
    backups = list(tmp_path.glob('existing.pre-roi-*.bak'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('SELECT qr FROM flow_jobs').fetchone()[0] == 'KEEP-ME'
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='station_configs'").fetchone() is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='station_configs'").fetchone()


def test_wrong_chunk_sequence_does_not_block_complete_color_inspection(client):
    qr = 'SEQ-1'
    sid = start(client, qr, 1).json()['id']
    rejected = client.post(f'/api/flow/recording/{sid}/1',
           files={'chunk': ('vid.webm', b'x' * 400, 'video/webm')})
    assert rejected.status_code == 409
    result = finish(client, sid, [['green'], ['green', 'red']], with_video=False)
    assert result['state'] == 'passed'
    assert result['can_handoff']


def test_interrupted_station_does_not_unlock(client):
    qr = 'JOB-STOP'
    sid = start(client, qr, 1).json()['id']
    abort = client.post(f'/api/flow/abort/{sid}')
    assert abort.status_code == 200
    assert start(client, qr, 2).status_code == 409
    assert start(client, qr, 1).status_code == 409
    assert start(client, 'NEXT-JOB-STOP', 1).status_code == 200


def test_wrong_order_is_latched_and_cannot_be_corrected(client):
    qr = 'WRONG-ORDER'
    sid = start(client, qr, 1).json()['id']
    result = hold(client, sid, ['red']).json()
    assert result['quarantined']
    summary = client.post('/api/flow/lookup', json={'qr': qr}).json()
    assert summary['quarantined']
    assert start(client, qr, 1).status_code == 409
    assert start(client, qr, 2).status_code == 409
    corrected = finish(client, sid, [['green'], ['green', 'red']])
    assert corrected['state'] == 'blocked'
    assert not corrected['can_handoff']
    db.initialize()
    assert start(client, qr, 1).status_code == 409


def test_missing_or_simultaneous_colors_are_blocked(client):
    sid = start(client, 'MISSING', 1).json()['id']
    assert finish(client, sid, [['green']])['state'] == 'blocked'
    assert start(client, 'MISSING', 1).status_code == 409
    sid = start(client, 'SIMULTANEOUS', 1).json()['id']
    assert hold(client, sid, ['green', 'red']).json()['quarantined']
    assert finish(client, sid, [['green', 'red']])['state'] == 'blocked'


def test_worker_page_and_qr_camera_fallback(client):
    response = client.get('/worker?station=2')
    assert response.status_code == 200
    assert 'worker.js' in response.text
    qr = cv2.QRCodeEncoder_create().encode('PHONE-QR-001')
    qr = cv2.copyMakeBorder(qr, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    qr = cv2.resize(qr, (500, 500), interpolation=cv2.INTER_NEAREST)
    _, encoded = cv2.imencode('.png', qr)
    response = client.post('/api/qr/decode', files={'frame': ('qr.png', encoded.tobytes(), 'image/png')})
    assert response.status_code == 200
    assert response.json()['qr'] == 'PHONE-QR-001'
    response = client.post('/api/qr/decode', files={'frame': ('blank.jpg', frame([]), 'image/jpeg')})
    assert response.json()['qr'] is None
    response = client.post('/api/qr/decode', files={'frame': ('bad.jpg', b'not an image', 'image/jpeg')})
    assert response.status_code == 400


def test_restart_closes_unfinished_count_check_as_interrupted(client):
    sid = start(client, 'RESTART-INTERRUPTED', 1).json()['id']
    production.active.clear()
    db.initialize()
    saved = client.get(f'/api/flow/attempts/{sid}').json()
    assert saved['state'] == 'interrupted'
    assert saved['ended_at']
    assert saved['result']['issues'] > 0
    assert start(client, 'RESTART-INTERRUPTED', 1).status_code == 409
    assert start(client, 'AFTER-RESTART', 1).status_code == 200


def test_admin_reads_real_worker_state_progress_and_final_result(client):
    empty = client.get('/api/flow/admin').json()
    assert empty['stats']['total_jobs'] == 0
    assert empty['attempts'] == []
    assert client.get('/admin').status_code == 200
    sid = start(client, 'REAL-ADMIN-01', 1).json()['id']
    running = client.get('/api/flow/admin')
    assert running.headers['cache-control'] == 'no-store'
    data = running.json()
    row = data['attempts'][0]
    assert (row['id'], row['qr'], row['operator'], row['station_id'], row['state']) == (
        sid, 'REAL-ADMIN-01', 'EMP-1', 1, 'active')
    assert data['stats']['running'] == 1
    assert data['stations'][0]['running'][0]['id'] == sid
    hold(client, sid, ['green'])
    progress = client.get('/api/flow/admin').json()['attempts'][0]
    assert progress['result']['verified'] == 1
    assert progress['result']['total'] == 2
    assert progress['frame_url'].endswith(f'flow_live_{sid}.jpg')
    assert (production.EVIDENCE / Path(progress['frame_url']).name).is_file()
    time.sleep(.025)
    result = finish(client, sid, [['green', 'red']])
    final = client.get('/api/flow/admin').json()
    row = final['attempts'][0]
    assert row['state'] == result['state'] == 'passed'
    assert row['video_url'] == result['video_url']
    assert row['recorded_bytes'] == (production.RECORDINGS / Path(row['video_url']).name).stat().st_size
    assert row['recorded_chunks'] == 1
    assert final['stats']['passed'] == 1
    assert final['stats']['running'] == 0
    assert final['stats']['completed_jobs'] == 0  # Station pass is not a finished workpiece.
    assert not final['stations'][0]['running']
    details = client.get(f'/api/flow/attempts/{sid}').json()
    assert [a['event'] for a in details['audit']] == ['started', 'passed']
    # Historical station names and SOP are snapshots, not today's changed config.
    production.STATIONS[0]['name'] = 'changed station'
    try:
        assert client.get(f'/api/flow/attempts/{sid}').json()['station']['name'] != 'changed station'
    finally:
        production.STATIONS[0]['name'] = details['station']['name']


def test_admin_shows_order_violation_immediately(client):
    sid = start(client, 'ADMIN-INCOMPLETE', 1).json()['id']
    hold(client, sid, ['red'])
    data = client.get('/api/flow/admin').json()
    assert data['attempts'][0]['state'] == 'blocked'
    assert data['stats']['quarantined'] == 1
    assert data['stats']['passed'] == 0
    assert data['attempts'][0]['result']['quarantined']
    client.post(f'/api/flow/abort/{sid}')
    production.active.clear()
    db.initialize()
    data = client.get('/api/flow/admin').json()
    assert data['stats']['total_jobs'] == 1
    assert data['stats']['running'] == 0
    assert data['stats']['quarantined'] == 1


def test_admin_filters_literal_search_pagination_and_validation(client):
    for qr in ['LITERAL_%', 'LITERAL_AB', 'THIRD']:
        sid = start(client, qr, 1).json()['id']
        client.post(f'/api/flow/abort/{sid}')
    exact = client.get('/api/flow/admin', params={'q':'_%'}).json()
    assert exact['total'] == 1 and exact['attempts'][0]['qr'] == 'LITERAL_%'
    first = client.get('/api/flow/admin', params={'limit':1,'offset':0,'state':'interrupted','station_id':1}).json()
    second = client.get('/api/flow/admin', params={'limit':1,'offset':1}).json()
    assert first['total'] == 3
    assert first['attempts'][0]['id'] != second['attempts'][0]['id']
    assert client.get('/api/flow/admin',params={'station_id':2}).json()['total'] == 0
    assert client.get('/api/flow/admin',params={'q':"' OR 1=1 --"}).json()['total'] == 0
    assert client.get('/api/flow/admin',params={'state':'invented'}).status_code == 400
    assert client.get('/api/flow/admin',params={'limit':0}).status_code == 422


def test_duplicate_start_and_chunk_do_not_duplicate_admin_data(client):
    body = {'qr':'IDEMPOTENT','station_id':1,'operator':'EMP-REAL',
            'mime_type':'video/webm','request_id':'request-unique-123456'}
    first = client.post('/api/flow/start',json=body).json()
    second = client.post('/api/flow/start',json=body).json()
    assert first['id'] == second['id']
    sid = first['id']
    assert client.get('/api/flow/requests/'+body['request_id']).json()['id'] == sid
    assert client.post('/api/flow/start',json={**body,'qr':'DIFFERENT'}).status_code == 409
    payload = b'video bytes' * 100
    for _ in range(2):
        assert client.post(f'/api/flow/recording/{sid}/0',files={'chunk':('part',payload)}).status_code == 200
    assert (production.RECORDINGS / f'{sid}.webm').read_bytes() == payload
    different = client.post(f'/api/flow/recording/{sid}/0',files={'chunk':('part',b'wrong' * 100)})
    assert different.status_code == 409
    row = client.get('/api/flow/admin').json()['attempts'][0]
    assert row['recorded_bytes'] == len(payload)
    assert row['recorded_chunks'] == 1
    assert client.get('/api/flow/admin').json()['stats']['total_attempts'] == 1
    assert len(client.get(f'/api/flow/attempts/{sid}').json()['audit']) == 1


def test_terminal_retries_preserve_result_and_exactly_one_audit(client):
    sid = start(client, 'TERMINAL-RETRY', 1).json()['id']
    result = finish(client, sid, [['green'],['green','red']])
    assert result['state'] == 'passed'
    assert client.post(f'/api/flow/finish/{sid}').json()['state'] == 'passed'
    assert client.post(f'/api/flow/abort/{sid}').json()['state'] == 'passed'
    details = client.get(f'/api/flow/attempts/{sid}').json()
    assert [a['event'] for a in details['audit']] == ['started','passed']
    assert client.get('/api/flow/admin').json()['stats']['passed'] == 1
    production.active.clear()
    db.initialize()
    assert client.post(f'/api/flow/abort/{sid}').json()['state'] == 'passed'


def test_missing_recording_file_does_not_change_inspection_pass(client):
    sid = start(client, 'FILE-LOSS', 1).json()['id']
    for markers in [['green'],['green','red']]:
        hold(client,sid,markers)
    client.post(f'/api/flow/recording/{sid}/0',files={'chunk':('part',b'x'*500)})
    (production.RECORDINGS / f'{sid}.webm').unlink()
    result = client.post(f'/api/flow/finish/{sid}').json()
    assert result['state'] == 'passed'
    assert result['inspection']['recording_error']
    row = client.get('/api/flow/admin').json()['attempts'][0]
    assert row['state'] == 'passed' and row['video_url'] is None


def test_concurrent_duplicate_start_creates_one_attempt(client):
    from concurrent.futures import ThreadPoolExecutor
    body = {'qr':'CONCURRENT','station_id':1,'operator':'EMP-C',
            'request_id':'concurrent-start-123456'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _:client.post('/api/flow/start',json=body), range(8)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()['id'] for r in responses}) == 1
    data = client.get('/api/flow/admin').json()
    assert data['stats']['total_attempts'] == data['stats']['total_jobs'] == 1


def test_disk_write_failure_does_not_increment_admin_bytes(client, monkeypatch):
    sid = start(client,'DISK-FAIL',1).json()['id']
    with monkeypatch.context() as m:
        def fail(_):
            raise OSError('simulated disk failure')
        m.setattr(production.os,'fsync',fail)
        with pytest.raises(OSError):
            client.post(f'/api/flow/recording/{sid}/0',files={'chunk':('part',b'x'*500)})
    row = client.get('/api/flow/admin').json()['attempts'][0]
    assert row['recorded_bytes'] == row['recorded_chunks'] == 0
    assert (production.RECORDINGS / f'{sid}.webm').stat().st_size == 0
    assert client.post(f'/api/flow/recording/{sid}/0',files={'chunk':('part',b'x'*500)}).status_code == 200


def test_mobile_gateway_and_desktop_use_same_backend(client):
    import httpx
    import mobile_gateway
    backend = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8000')
    mobile_gateway.app.state.backend = backend
    # No gateway lifespan here: inject the same in-process backend used by desktop.
    mobile = TestClient(mobile_gateway.app)
    mobile.cookies.update(client.cookies)
    mobile.headers["X-CSRF-Token"]=client.headers["X-CSRF-Token"]
    try:
        response = mobile.post('/api/flow/start',json={'qr':'MOBILE-TO-ADMIN','station_id':1,
                  'operator':'PHONE-EMP','request_id':'mobile-unique-123456'})
        assert response.status_code == 200, response.text
        sid = response.json()['id']
        row = client.get('/api/flow/admin',params={'q':'MOBILE-TO-ADMIN'}).json()['attempts'][0]
        assert row['id'] == sid and row['operator'] == 'PHONE-EMP'
        hold(client,sid,['green'])
        assert mobile.get('/api/flow/admin').json()['attempts'][0]['result']['verified'] == 1
        assert mobile.post(f'/api/flow/abort/{sid}').json()['state'] == 'interrupted'
        assert client.get('/api/flow/admin').json()['stats']['quarantined'] == 1
        assert mobile.get('/api/flow/admin',params={'q':'NO-SUCH-JOB'}).json()['total'] == 0
        assert mobile.get('/admin').status_code == 200
        scanned = mobile.post('/api/qr/decode',files={'frame':('blank.jpg',frame([]),'image/jpeg')})
        assert scanned.status_code == 200 and scanned.json()['qr'] is None
        ranged = mobile.get('/static/worker.js',headers={'range':'bytes=0-29'})
        assert ranged.status_code == 206
        assert ranged.content == (Path(__file__).resolve().parents[1] / 'static' / 'worker.js').read_bytes()[:30]
        # A malicious Host or absolute-looking path cannot change the upstream origin.
        assert mobile.get('/api/health',headers={'host':'attacker.example'}).json()['ok']
    finally:
        import asyncio
        asyncio.run(backend.aclose())
        mobile.close()


def test_admin_legacy_recording_reports_unknown_counts_and_missing_files(client):
    with db.connect() as c:
        c.execute("INSERT INTO flow_jobs(qr,created_at) VALUES('LEGACY',?)", (production.utcnow(),))
        c.execute('''INSERT INTO flow_attempts(id,qr,station_id,operator,state,started_at,ended_at,video_url)
                     VALUES('legacy-id','LEGACY',1,'OLD-EMP','passed',?,?,?)''',
                  (production.utcnow(),production.utcnow(),'/media/recordings/legacy.webm'))
    row = client.get('/api/flow/admin').json()['attempts'][0]
    assert row['recording_available'] is False
    assert row['recorded_chunks'] is None and row['recorded_bytes'] is None
    (production.RECORDINGS / 'legacy.webm').write_bytes(b'old recording')
    row = client.get('/api/flow/attempts/legacy-id').json()
    assert row['recording_available'] is True
    assert row['recorded_bytes'] == len(b'old recording')
    assert row['recorded_chunks'] is None


def test_mobile_gateway_returns_error_when_main_backend_unavailable(client):
    import asyncio
    import httpx
    import mobile_gateway
    async def disconnected(request):
        raise httpx.ConnectError('connection lost',request=request)
    backend = httpx.AsyncClient(transport=httpx.MockTransport(disconnected),base_url='http://127.0.0.1:8000')
    mobile_gateway.app.state.backend = backend
    mobile = TestClient(mobile_gateway.app)
    mobile.cookies.update(client.cookies)
    mobile.headers["X-CSRF-Token"]=client.headers["X-CSRF-Token"]
    try:
        response = mobile.post('/api/flow/start',json={'qr':'OFFLINE','station_id':1,'operator':'EMP'})
        assert response.status_code == 502
        assert 'detail' in response.json()
        assert client.get('/api/flow/admin').json()['stats']['total_attempts'] == 0
    finally:
        asyncio.run(backend.aclose())
        mobile.close()
