"""Recovery, concurrent storage and exclusive backend startup contracts."""
import asyncio
import io
import subprocess
import sys
import threading

import pytest
from fastapi import UploadFile

import cameras
import db
from runtime_guard import BackendGuard
from test_cameras import camera_client, open_cam


def test_database_readers_continue_during_uncommitted_write(camera_client):
    with db.connect() as writer, db.connect() as reader:
        assert writer.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert writer.execute('PRAGMA synchronous').fetchone()[0] == 2
        writer.execute('BEGIN IMMEDIATE')
        writer.execute("INSERT INTO flow_jobs(qr,created_at) VALUES('UNCOMMITTED', '2026-01-01')")
        assert reader.execute("SELECT count(*) FROM flow_jobs WHERE qr='UNCOMMITTED'").fetchone()[0] == 0
        writer.commit()
        assert reader.execute("SELECT count(*) FROM flow_jobs WHERE qr='UNCOMMITTED'").fetchone()[0] == 1


def test_second_process_cannot_recover_an_in_use_database(tmp_path):
    path = tmp_path / 'production.db'
    source = ('from runtime_guard import BackendGuard; '
              'import sys; BackendGuard(sys.argv[1]).__enter__()')
    with BackendGuard(path):
        result = subprocess.run([sys.executable, '-c', source, str(path)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'already uses this database' in result.stderr
    with BackendGuard(path):
        pass  # Restart succeeds immediately after releasing the first owner.


def test_disk_sync_does_not_freeze_the_async_server(camera_client, monkeypatch):
    body = open_cam(camera_client)
    entered, release = threading.Event(), threading.Event()
    original = cameras.os.fsync

    def delayed_sync(fd):
        entered.set()
        assert release.wait(2), 'Event loop was blocked by disk synchronization'
        return original(fd)

    monkeypatch.setattr(cameras.os, 'fsync', delayed_sync)

    async def scenario():
        upload = asyncio.create_task(cameras.chunk(body['id'], 0, 0,
            UploadFile(io.BytesIO(b'camera-data')), body['token']))
        try:
            # The event loop can service other requests while disk IO waits.
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            assert entered.is_set()
            assert not upload.done()
        finally:
            release.set()
        assert (await upload)['bytes'] == len(b'camera-data')

    asyncio.run(scenario())


def test_stale_cameras_close_without_an_admin_poll(camera_client):
    body = open_cam(camera_client)
    with db.connect() as c:
        c.execute("UPDATE camera_sessions SET last_seen='2020-01-01T00:00:00+00:00' WHERE id=?", (body['id'],))
    assert cameras.expire_stale() == [body['id']]
    with db.connect() as c:
        assert c.execute('SELECT state FROM camera_sessions WHERE id=?', (body['id'],)).fetchone()[0] == 'interrupted'


def test_retry_close_cannot_change_the_recorded_outcome(camera_client):
    body = open_cam(camera_client)
    path = f'/api/cameras/{body["id"]}/close'
    assert camera_client.post(path, json={'token': body['token'], 'error': 'disconnected'}).json()['state'] == 'interrupted'
    assert camera_client.post(path, json={'token': body['token']}).json()['state'] == 'interrupted'
