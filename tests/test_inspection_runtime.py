"""Reject mixed client/server versions before opening a production job."""
import main
from test_production_flow import client


def test_inspection_runtime_reports_batch_protocol(client):
    result=client.get('/api/health').json()
    assert result['frame_protocol']==2
    assert result['inspection_engine']=='color-count-2'
    assert not result['needs_restart']


def test_changed_sources_require_restart(client,monkeypatch):
    monkeypatch.setattr(main,'INSPECTION_BUILD','previous-running-build')
    assert client.get('/api/health').json()['needs_restart']
