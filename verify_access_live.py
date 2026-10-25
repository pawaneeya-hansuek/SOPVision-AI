import json,ssl,urllib.request,urllib.error
import db,auth
from pathlib import Path
for base in ('http://127.0.0.1:8000','http://127.0.0.1:8001','https://127.0.0.1:8443'):
 context=ssl._create_unverified_context() if base.startswith('https') else None
 for route in ('/api/health','/api/auth/status','/api/flow/admin','/api/flow/admin/export?format=csv','/media/evidence/private.jpg'):
  try:
   with urllib.request.urlopen(base+route,context=context,timeout=10) as response:status=response.status;data=json.loads(response.read()) if route.startswith('/api/auth/status') else None
  except urllib.error.HTTPError as e:status=e.code;data=None
  expected=200 if route in ('/api/health','/api/auth/status') else 401
  assert status==expected,(base,route,status)
  print(base,route,status)
  if data is not None:assert data['configured'] is False
with db.connect() as c:
 print('Production attempts preserved:',c.execute('SELECT count(*) FROM flow_attempts').fetchone()[0])
 print('Users:',c.execute('SELECT count(*) FROM users').fetchone()[0])
 print('Seeded review queue:',c.execute('SELECT count(*) FROM supervisor_reviews').fetchone()[0])
 assert c.execute('SELECT count(*) FROM flow_attempts').fetchone()[0]==18
 assert c.execute('SELECT count(*) FROM users').fetchone()[0]==0
assert auth.setup_path().exists()
assert list(Path(db.DB).parent.glob('sopvision.pre-access-*.bak')) or list((Path(db.DB).parent/'backups/legacy').glob('sopvision.pre-access-*.bak'))
print('PASS: same authenticated backend on all 3 entries, migration backup, original data retained, first-admin setup ready')
