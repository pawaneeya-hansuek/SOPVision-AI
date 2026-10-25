"""Archived recordings play as finite-duration H.264 MP4 with byte-range seeks."""
import hashlib
from pathlib import Path
import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
import playback


def source_video(tmp_path):
    source=tmp_path/'recordings'/'camera.webm';source.parent.mkdir()
    writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'VP80'),10,(320,240))
    assert writer.isOpened()
    for n in range(20):
        frame=np.full((240,320,3),(40,180,60),np.uint8)
        cv2.putText(frame,str(n),(50,100),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        writer.write(frame)
    writer.release()
    return source


def test_browser_copy_has_duration_and_index_without_changing_original(tmp_path,monkeypatch):
    monkeypatch.setattr(playback,'CACHE',tmp_path/'playback')
    source=source_video(tmp_path);before=hashlib.sha256(source.read_bytes()).hexdigest()
    target=playback.browser_video(source)
    assert target!=source and target.suffix=='.mp4'
    data=target.read_bytes();assert data[4:8]==b'ftyp' and b'avc1' in data
    assert data.index(b'moov')<data.index(b'mdat')
    cap=cv2.VideoCapture(str(target))
    assert cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT)==20
    assert cap.get(cv2.CAP_PROP_FPS)==10
    cap.release()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert playback.browser_video(source)==target
    assert not list(playback.CACHE.glob('*.tmp.mp4'))


def test_archive_url_serves_mp4_and_supports_range_seeking(tmp_path,monkeypatch):
    monkeypatch.setattr(playback,'CACHE',tmp_path/'playback')
    source_video(tmp_path)
    app=FastAPI();app.mount('/media',playback.RecordedMedia(directory=tmp_path))
    with TestClient(app) as c:
        response=c.get('/media/recordings/camera.webm')
        assert response.status_code==200,response.text
        assert response.headers['content-type']=='video/mp4'
        assert response.content[4:8]==b'ftyp'
        partial=c.get('/media/recordings/camera.webm',headers={'Range':'bytes=100-199'})
        assert partial.status_code==206 and len(partial.content)==100
        assert partial.content==response.content[100:200]
        assert partial.headers['content-range']==f'bytes 100-199/{len(response.content)}'


def test_traversal_does_not_escape_the_media_directory(tmp_path):
    app=FastAPI();app.mount('/media',playback.RecordedMedia(directory=tmp_path))
    with TestClient(app) as c:
        assert c.get('/media/recordings/../../../main.py').status_code==404
