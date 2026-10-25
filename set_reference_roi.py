"""Calibrate station 1 from the owner's portrait reference, without changing results."""
from pathlib import Path
from datetime import datetime,timezone
import copy,json,sqlite3
import cv2
import db,production
from vision import Tracker,_pixel_roi,_contains

ROOT=Path(__file__).parent
reference=ROOT/'.roi-reference/roi-settings.png'
image=cv2.imread(str(reference))
if image is None:raise RuntimeError('Reference image unavailable')
current=production.station_for(1)
proposed=copy.deepcopy(current)
base_roi={'x':0.25,'y':0.31,'w':0.49,'h':0.49}
red_roi={'x':0.25,'y':0.58,'w':0.49,'h':0.23}
proposed['anchor']['roi']=base_roi.copy()
proposed['anchor']['min_area_ratio']=0.20
for step in proposed['steps']:
    if step['color']=='green':
        step.update(roi=base_roi.copy(),min_area_ratio=0.20,max_area_ratio=0.95,
                    min_aspect_ratio=0.50,max_aspect_ratio=1.40)
    elif step['color']=='red':
        step.update(roi=red_roi.copy(),min_area_ratio=0.35,max_area_ratio=0.95,
                    min_aspect_ratio=1.20,max_aspect_ratio=1.90,
                    relative_to_anchor=[-0.20,0.20,0.15,1.05])
body=production.StationConfigIn(expected_version=current['version'],
                               anchor=proposed['anchor'],steps=proposed['steps'])
config=body.model_dump(exclude={'expected_version'})
for roi in [config['anchor']['roi'],*[s['roi'] for s in config['steps']]]:
    assert roi['x']+roi['w']<=1 and roi['y']+roi['h']<=1
assert all(s['min_area_ratio']<s['max_area_ratio'] for s in config['steps'])
assert [(s['id'],s['name'],s['color']) for s in config['steps']]==[(s['id'],s['name'],s['color']) for s in current['steps']]

# Check both the original image and the width used by the live worker.
for width in (image.shape[1],640):
    frame=cv2.resize(image,(width,round(image.shape[0]*width/image.shape[1])))
    tracker=Tracker(config['steps'],anchor=config['anchor'],configuration_version=current['version']+1)
    visible,_=tracker.feed(frame,0.0)
    assert visible['green']['anchor_valid'],visible
    assert all(visible[color]['installed_position'] for color in ('green','red')),visible
    red=visible['red']['bbox'].copy();red[1]-=round(frame.shape[0]*0.25)
    assert not _contains(_pixel_roi(frame,red_roi),red),'A red piece above the target must fail'
    print('Reference geometry matches at width',width)
    # A final assembled photo cannot establish the order of work.
    for n in range(1,16):tracker.feed(frame,n*.1)
    result=tracker.snapshot()
    assert result['verified']<result['total'],'Static assembled image must not prove sequence'

stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path(db.DB).with_name('sopvision.pre-reference-roi-'+stamp+'.bak')
with db.connect() as c,sqlite3.connect(backup) as target:c.backup(target)
(ROOT/'.roi-reference/station1-before.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
with db.connect() as c:
    c.execute('BEGIN IMMEDIATE')
    running=c.execute('SELECT count(*) FROM flow_attempts WHERE station_id=1 AND ended_at IS NULL').fetchone()[0]
    if running:raise RuntimeError('Station 1 has active work; finish it before changing ROI')
    before_others=[tuple(r) for r in c.execute('SELECT * FROM station_configs WHERE station_id<>1 ORDER BY station_id')]
    row=c.execute('SELECT version FROM station_configs WHERE station_id=1').fetchone()
    version=row['version'] if row else 0
    if version!=body.expected_version:raise RuntimeError('Configuration changed; reload before saving')
    saved=version+1;now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    c.execute("""INSERT INTO station_configs(station_id,version,config_json,updated_at) VALUES(1,?,?,?)
       ON CONFLICT(station_id) DO UPDATE SET version=excluded.version,config_json=excluded.config_json,updated_at=excluded.updated_at""",
       (saved,json.dumps(config,ensure_ascii=False),now))
    c.execute("INSERT INTO security_audit(actor_id,event,target,detail,happened_at) VALUES(NULL,?,?,?,?)",
              ('roi_reference_updated','station:1',json.dumps({'previous_version':version,'version':saved,
               'reference':'image(4).png','base_roi':base_roi,'red_roi':red_roi},ensure_ascii=False),now))
    after_others=[tuple(r) for r in c.execute('SELECT * FROM station_configs WHERE station_id<>1 ORDER BY station_id')]
    assert before_others==after_others
assert production.station_for(1)['version']==saved
print('Saved station 1 ROI version',saved,'; stations 2 and 3 unchanged; existing inspection results preserved.')
