"""Replay the assembly clip which exposed hand/camera and cover ROI failures."""
from pathlib import Path
import cv2
import numpy as np
import pytest
import time
import production
from test_production_flow import client
from calibration_profiles import comfortable_station_one
from production import STATIONS
from vision import Tracker

VIDEO = Path(__file__).parent / 'fixtures' / 'station1-assembly.mp4'


def tracker():
    profile = comfortable_station_one(STATIONS[0])
    return Tracker(profile['steps'], anchor=profile['anchor'])


def read_frame(cap, second, width=640):
    cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
    ok, frame = cap.read()
    assert ok
    frame = cv2.resize(frame, (width, round(frame.shape[0] * width / frame.shape[1])))
    # The live browser sends JPEG frames, unlike offline video decoding.
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 76])
    assert ok
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


@pytest.mark.parametrize('fps,width', [(10, 640), (12, 640), (10, 320)])
def test_recorded_correct_assembly_survives_hands_and_cover_placement(fps, width):
    cap = cv2.VideoCapture(str(VIDEO))
    tr = tracker()
    try:
        for n in range(10 * fps):
            tr.feed(read_frame(cap, n / fps, width), n / fps)
    finally:
        cap.release()
    result = tr.snapshot(final=True)
    assert result['status'] == 'pass', result
    assert not result['camera_moved']
    assert [event['color'] for event in result['events']] == ['green', 'red']


@pytest.mark.parametrize('mode', ['assembled_photo', 'reverse'])
def test_recorded_simultaneous_or_reversed_colors_fail_order(mode):
    cap = cv2.VideoCapture(str(VIDEO))
    tr = tracker()
    try:
        final = read_frame(cap, 9.5)
        red_only = final.copy()
        red_only[330:600, 147:486] = (185, 185, 185)
        first = final if mode == 'assembled_photo' else red_only
        for n in range(15):
            tr.feed(first, n / 10)
        for n in range(15):
            tr.feed(final, 1.5 + n / 10)
    finally:
        cap.release()
    result = tr.snapshot(final=True)
    assert result['status'] == 'review', result
    assert result['steps'][1]['status'] == 'out_of_order'


@pytest.mark.parametrize('mode', ['missing_cover', 'covered_final'])
def test_unseen_colors_fail_but_completed_colors_survive_occlusion(mode):
    cap = cv2.VideoCapture(str(VIDEO))
    tr = tracker()
    try:
        base = read_frame(cap, 5.0)
        final = read_frame(cap, 9.5)
        if mode == 'covered_final':
            for n in range(100):
                tr.feed(read_frame(cap, n / 10), n / 10)
            blocked = final.copy()
            cv2.rectangle(blocked, (140, 570), (490, 950), (180, 180, 180), -1)
            for n in range(10):
                tr.feed(blocked, 10 + n / 10)
        else:
            red_only = final.copy()
            red_only[330:600, 147:486] = (185, 185, 185)
            first = base
            for n in range(15):
                tr.feed(first, n / 10)
            for n in range(15):
                tr.feed(base if mode == 'missing_cover' else final, 1.5 + n / 10)
    finally:
        cap.release()
    assert tr.snapshot(final=True)['status'] == ('pass' if mode=='covered_final' else 'review'), tr.snapshot(final=True)


def test_recorded_clip_through_worker_frame_recording_and_handoff_routes(client):
    profile = comfortable_station_one(production.station_for(1))
    config = production.StationConfigIn(expected_version=profile['version'],
                                       anchor=profile['anchor'], steps=profile['steps'])
    response = client.put('/api/flow/stations/1/config', json=config.model_dump())
    assert response.status_code == 200, response.text
    response = client.post('/api/flow/start', json={
        'qr': 'RECORDED-ASSEMBLY-REGRESSION', 'station_id': 1,
        'operator': 'TEST', 'mime_type': 'video/mp4'})
    assert response.status_code == 200, response.text
    sid = response.json()['id']
    cap = cv2.VideoCapture(str(VIDEO))
    try:
        for n in range(100):
            frame = read_frame(cap, n / 10)
            ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
            assert ok
            production.active[sid]['started'] = time.monotonic() - n / 10
            response = client.post('/api/flow/frame/' + sid,
                                   files={'frame': ('frame.jpg', data.tobytes(), 'image/jpeg')})
            assert response.status_code == 200, response.text
    finally:
        cap.release()
    response = client.post('/api/flow/recording/' + sid + '/0',
                           files={'chunk': ('recording.mp4', VIDEO.read_bytes(), 'video/mp4')})
    assert response.status_code == 200, response.text
    response = client.post('/api/flow/finish/' + sid)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['state'] == 'passed', result
    assert result['can_handoff']
    assert result['job']['stations'][1]['state'] == 'ready'


def test_same_clip_through_upload_analyzer(monkeypatch):
    import main
    monkeypatch.setattr(main, 'remember_evidence', lambda *args: '/test-evidence.jpg')
    profile = comfortable_station_one(STATIONS[0])
    profile['version'] = 6
    result = main.analyze_video(VIDEO, 'clip-regression', profile)
    assert result['status'] == 'pass', result
    assert result['verified'] == 2
