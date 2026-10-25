import sys
sys.path.insert(0,'.test-deps')
import httpx
for base in ('http://127.0.0.1:8000','http://127.0.0.1:8001','https://127.0.0.1:8443'):
    with httpx.Client(base_url=base,verify=False,timeout=15) as c:
        c.get('/api/worker/session').raise_for_status()
        c.headers['X-Worker-Mode']='station'
        r=c.get('/api/flow/stations');r.raise_for_status()
        stations=r.json();s=next(s for s in stations if s['id']==1)
        assert s['version']==6
        assert all(step['stable_seconds']==.4 for step in s['steps'])
        assert next(step for step in s['steps'] if step['color']=='red')['roi']=={'x':.23,'y':.50,'w':.53,'h':.32}
        assert s['anchor']['roi']=={'x':.23,'y':.29,'w':.53,'h':.53}
        assert next(s for s in stations if s['id']==2)['version']==0
        assert next(s for s in stations if s['id']==3)['version']==0
        print(base+': station 1 profile v6, 0.4s dwell, stations 2-3 preserved')
