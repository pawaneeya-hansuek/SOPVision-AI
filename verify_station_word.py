import sys
sys.path.insert(0,'.test-deps')
import httpx
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=15) as c:
    page=c.get('/worker')
    assert page.status_code==200 and 'สเตชั่น' in page.text and 'สถานี' not in page.text
    c.get('/api/worker/session')
    c.headers['X-Worker-Mode']='station'
    stations=c.get('/api/flow/stations').json()
    assert len(stations)==3
    assert all('สเตชั่น' in s['name'] and 'สถานี' not in s['name'] for s in stations)
print('PASS: live worker labels and all 3 configured station names use the requested wording.')
