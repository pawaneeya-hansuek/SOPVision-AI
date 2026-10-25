import sys,json,sqlite3,urllib.request
sys.path.insert(0,'.test-deps')
import db
with db.connect() as c:
 print('Open production attempts:',c.execute('SELECT count(*) FROM flow_attempts WHERE ended_at IS NULL').fetchone()[0])
 print('Existing attempts:',c.execute('SELECT count(*) FROM flow_attempts').fetchone()[0])
 print('Configured admin table:',bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()))
for url in ('http://127.0.0.1:8000','http://127.0.0.1:8001'):
 with urllib.request.urlopen(url+'/api/health',timeout=10) as r:print(url,'health',r.status)
with urllib.request.urlopen('http://127.0.0.1:8000/api/cameras',timeout=10) as r:
 cameras=json.load(r)['cameras'];print('Online cameras:',sum(bool(c.get('online')) for c in cameras))
