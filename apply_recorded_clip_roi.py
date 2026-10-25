"""Commit the tested profile while no station work is active."""
from pathlib import Path
from datetime import datetime,timezone
import json,sqlite3
import cv2
import db,production
from vision import Tracker
from calibration_profiles import comfortable_station_one

ROOT=Path(__file__).parent
current=production.station_for(1)
if current['version']!=5:raise RuntimeError('ROI changed since calibration; reload before applying')
proposed=comfortable_station_one(current)
body=production.StationConfigIn(expected_version=current['version'],anchor=proposed['anchor'],steps=proposed['steps'])
config=body.model_dump(exclude={'expected_version'})
for roi in [config['anchor']['roi'],*[s['roi'] for s in config['steps']]]:
    assert roi['x']+roi['w']<=1 and roi['y']+roi['h']<=1
assert all(s['min_area_ratio']<s['max_area_ratio'] and s['min_aspect_ratio']<s['max_aspect_ratio'] for s in config['steps'])
reference=cv2.imread(str(ROOT/'.roi-reference/roi-settings.png'))
assert reference is not None
tracker=Tracker(config['steps'],anchor=config['anchor'])
visible,_=tracker.feed(reference,.01)
assert all(visible[c]['installed_position'] for c in ('green','red'))
for n in range(1,12):tracker.feed(reference,.01+n*.1)
assert tracker.snapshot(final=True)['status']=='review','A static assembled photo cannot establish work order'
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path(db.DB).with_name('sopvision.pre-recorded-clip-fix-'+stamp+'.bak')
with db.connect() as c,sqlite3.connect(backup) as target:c.backup(target)
with db.connect() as c:
    c.execute('BEGIN IMMEDIATE')
    if c.execute('SELECT count(*) FROM flow_attempts WHERE ended_at IS NULL').fetchone()[0]:
        raise RuntimeError('Work is active; finish current work before applying')
    stored=c.execute('SELECT version FROM station_configs WHERE station_id=1').fetchone()
    if stored['version']!=body.expected_version:raise RuntimeError('ROI changed concurrently')
    before_others=[tuple(r) for r in c.execute('SELECT * FROM station_configs WHERE station_id<>1 ORDER BY station_id')]
    version=stored['version']+1;now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    c.execute('UPDATE station_configs SET version=?,config_json=?,updated_at=? WHERE station_id=1',
              (version,json.dumps(config,ensure_ascii=False),now))
    c.execute('INSERT INTO security_audit(actor_id,event,target,detail,happened_at) VALUES(NULL,?,?,?,?)',
              ('recorded_clip_roi_updated','station:1',json.dumps({'version':version,'previous_version':stored['version'],
               'stable_seconds':.4,'base_roi':config['anchor']['roi'],'red_roi':config['steps'][1]['roi'],
               'sequence_and_final_presence_required':True},ensure_ascii=False),now))
    assert before_others==[tuple(r) for r in c.execute('SELECT * FROM station_configs WHERE station_id<>1 ORDER BY station_id')]
print('Applied station 1 profile version',version,'for tested cover position; other station profiles and existing results unchanged.')
