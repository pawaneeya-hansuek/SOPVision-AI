"""Read-only checks of deployed entry points and pre-deployment record counts."""
import json
import ssl
from pathlib import Path
import httpx
import db
from start_mobile import local_addresses

root = Path(__file__).resolve().parent
backups = sorted((root / 'backups').glob('stability-*/counts.json'))
expected = json.loads(backups[-1].read_text(encoding='utf-8'))
with db.connect() as c:
    assert c.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    assert c.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    for table, count in expected.items():
        assert c.execute(f'SELECT count(*) FROM {table}').fetchone()[0] >= count, table
with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=5) as desktop:
    health=desktop.get('/api/health').json()
    assert health['ok'] and health['frame_protocol']==2 and not health['needs_restart'],health
    assert desktop.get('/worker').status_code == 200
    worker=desktop.get('/worker').text
    assert 'expandCamera' in worker and 'worker.js?v=prior-station-check-9' in worker
    assert 'priorCheck' in worker
    assert health['instant_completion']
    assert 'processed_frames!==frames.length' in desktop.get('/static/worker.js').text
    assert desktop.get('/supervisor').status_code == 303
    assert desktop.get('/api/supervisor/recordings').status_code == 401
    assert desktop.get('/api/flow/admin').status_code == 401
context = ssl.create_default_context(cafile=str(root / '.certs/sopvision-ca.crt'))
with httpx.Client(base_url='https://127.0.0.1:8443', verify=context, trust_env=False, timeout=5) as phone:
    mobile_health=phone.get('/api/health').json()
    assert mobile_health==health
    assert phone.get('/worker').status_code == 200
    assert phone.get('/supervisor').status_code == 303
    assert phone.get('/api/supervisor/recordings').status_code == 401
    assert phone.get('/api/flow/admin').status_code == 401
print('PASS: deployed desktop and verified HTTPS mobile entry; auth enforced; DB integrity, WAL and record counts preserved')
for address in local_addresses():
    if address != '127.0.0.1':
        print(f'Mobile URL: https://{address}:8443/worker')
