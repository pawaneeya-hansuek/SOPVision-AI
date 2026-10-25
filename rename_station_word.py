from pathlib import Path
from datetime import datetime
import shutil
root=Path(__file__).parent
backup=root/'backups'/('station-word-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
files=[*root.joinpath('static').glob('*.html'),*root.joinpath('static').glob('*.js')]
files += [root/name for name in ('main.py','production.py','cameras.py','reporting.py','workflows.py','auth.py','station_access.py','vision.py','gemini_review.py','mobile_gateway.py')]
changed=0
for p in files:
    s=p.read_text(encoding='utf-8')
    if 'สถานี' not in s:continue
    rel=p.relative_to(root);dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,dest)
    changed+=s.count('สถานี')
    s=s.replace('สถานี','สเตชั่น')
    if p.suffix=='.html':
        for old in ('?v=copy-6','?v=station-5'):s=s.replace(old,'?v=word-7')
    p.write_text(s,encoding='utf-8')
# Stored configuration and old inspection snapshots keep their original bytes.
# Normalize their station name only when preparing display/export data.
p=root/'production.py';s=p.read_text(encoding='utf-8')
s=s.replace("            configured_steps = station.get('steps', [])","            station['name']=station['name'].replace('สถานี','สเตชั่น')\n            configured_steps = station.get('steps', [])")
s=s.replace("def start_response(sid, qr, station):","def start_response(sid, qr, station):\n    station={**station,'name':station['name'].replace('สถานี','สเตชั่น')}")
s=s.replace("    row['station'] = json.loads(row.pop('station_json') or 'null') or station_for(row['station_id'])","    row['station'] = json.loads(row.pop('station_json') or 'null') or station_for(row['station_id'])\n    row['station']['name']=row['station']['name'].replace('สถานี','สเตชั่น')")
p.write_text(s,encoding='utf-8')
print('Updated',changed,'visible wording occurrences; stored records preserved.')
