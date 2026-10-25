"""Read-only live parity check; does not create production jobs."""
import sys,ssl,csv,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.test-deps'))
import httpx
verify=ssl.create_default_context(cafile=str(ROOT/'.certs'/'sopvision-ca.crt'))
origins=['http://127.0.0.1:8000','http://127.0.0.1:8001','https://127.0.0.1:8443']
stats=[]
for origin in origins:
    with httpx.Client(base_url=origin,verify=verify,trust_env=False,timeout=20) as c:
        overview=c.get('/api/stats');overview.raise_for_status()
        admin=c.get('/api/flow/admin');admin.raise_for_status()
        assert overview.json()['production']==admin.json()['stats']
        response=c.get('/api/flow/admin/export');response.raise_for_status()
        exported=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert len(exported)==admin.json()['total']
        assert c.get('/api/flow/admin/export?format=html').status_code==200
        assert c.get('/api/records').status_code==200
        assert 'exportCsv' in c.get('/admin').text
        assert 'refreshWorkerHistory' in c.get('/static/worker.js').text
        stats.append(admin.json()['stats'])
        print(origin, 'OK, exported',len(exported),'attempts')
assert all(s==stats[0] for s in stats)
print('PASS: desktop, compatibility port and trusted mobile HTTPS share the same production totals')
