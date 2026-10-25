import sys
sys.path.insert(0,'.test-deps')
import httpx
for base in ('http://127.0.0.1:8000','http://127.0.0.1:8001','https://127.0.0.1:8443'):
    with httpx.Client(base_url=base,verify=False,timeout=15) as client:
        assert client.get('/worker').status_code==200
        first=client.get('/api/flow/admin')
        assert first.status_code==401,(base,first.status_code)
        entry=client.get('/api/worker/session')
        assert entry.status_code==200 and entry.json()['guest']
        client.headers['X-Worker-Mode']='station'
        assert client.get('/api/flow/stations').status_code==200
        assert client.get('/api/flow/my-history?station_id=1').status_code==200
        assert client.get('/api/flow/admin').status_code==403
        assert client.get('/api/users').status_code==403
        print(base+': worker accessible without login; station APIs work; admin still protected')
print('PASS: no production work created by verification.')
