from pathlib import Path
from datetime import datetime,timezone
import shutil
root=Path(__file__).resolve().parent
backup=root/'backups'/('access-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
backup.mkdir(parents=True)
names=['db.py','production.py','main.py','cameras.py','reporting.py','mobile_gateway.py','static/index.html','static/worker.html','static/admin.html','static/worker.js','static/app.js','static/production.js']
for name in names:
    target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,target)
def write(name,fn):
    p=root/name;s=p.read_text(encoding='utf-8');p.write_text(fn(s),encoding='utf-8')
def once(s,old,new):
    assert s.count(old)==1,(old[:100],s.count(old))
    return s.replace(old,new,1)
def database(s):
    s=once(s,'def initialize():\n    backup_before_schema_change()',"""def initialize():
    if DB.exists():
        with sqlite3.connect(DB) as source:
            names={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if names and 'users' not in names:
                stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                with sqlite3.connect(DB.with_name(DB.stem+'.pre-access-'+stamp+'.bak')) as target:
                    source.backup(target)
    backup_before_schema_change()""")
    s=once(s,'        # Only the single production backend calls initialize;',"""        import auth,workflows
        auth.initialize_schema(c)
        workflows.initialize_schema(c)
        # Only the single production backend calls initialize;""")
    return s
write('db.py',database)
def production(s):
    s=once(s,"    quarantined = any(r['state'] in ('blocked', 'interrupted') for r in rows)","""    from workflows import approved_attempts
    approved=approved_attempts(c,qr)
    quarantined = any(r['state'] in ('blocked', 'interrupted') and r['id'] not in approved for r in rows)""")
    s=once(s,"        elif last and last['state'] in ('blocked', 'interrupted'):\n            state = 'blocked'","""        elif last and last['state'] in ('blocked', 'interrupted'):
            state = ('ready' if n==1 or (n-1) in passed else 'locked') if last['id'] in approved else 'blocked'""")
    s=once(s,"    return {'qr': qr, 'exists': bool(rows), 'quarantined': quarantined,","""    job=c.execute('SELECT is_test,source_qr,test_run_id FROM flow_jobs WHERE qr=?',(qr,)).fetchone()
    return {'qr': qr, 'source_qr':job['source_qr'] if job else qr,
            'test_mode':bool(job['is_test']) if job else False,
            'test_run_id':job['test_run_id'] if job else None,
            'exists': bool(rows), 'quarantined': quarantined,""")
    s=once(s,"class Lookup(BaseModel):\n    qr: str = Field(min_length=1, max_length=300)","""class Lookup(BaseModel):
    qr: str = Field(min_length=1, max_length=300)
    test_mode: bool = False
    test_run_id: str | None = Field(default=None,max_length=80)""")
    s=once(s,"def lookup(body: Lookup):\n    qr = clean_qr(body.qr)\n    with db.connect() as c:\n        return status_for(c, qr)","""def lookup(body: Lookup):
    from workflows import job_key
    source=clean_qr(body.qr)
    qr=job_key(source,body.test_mode,body.test_run_id)
    with db.connect() as c:
        result=status_for(c,qr)
    result.update(source_qr=source,test_mode=body.test_mode,test_run_id=body.test_run_id)
    return result""")
    s=once(s,"class Start(BaseModel):\n    qr: str = Field(min_length=1, max_length=300)","""class Start(BaseModel):
    qr: str = Field(min_length=1, max_length=300)
    test_mode: bool = False
    test_run_id: str | None = Field(default=None,max_length=80)""")
    s=once(s,"    return {'id': sid, 'qr': qr, 'station': station, 'sample_every_ms': LIVE_SAMPLE_MS,","""    with db.connect() as c:
        job=c.execute('SELECT source_qr,is_test,test_run_id FROM flow_jobs WHERE qr=?',(qr,)).fetchone()
    return {'id': sid, 'qr': qr, 'source_qr':job['source_qr'] if job else qr,
            'test_mode':bool(job['is_test']) if job else False,
            'test_run_id':job['test_run_id'] if job else None,
            'station': station, 'sample_every_ms': LIVE_SAMPLE_MS,""")
    s=once(s,"def start_work(body: Start):\n    qr = clean_qr(body.qr)","""def start_work(body: Start):
    import auth
    from workflows import job_key
    source_qr=clean_qr(body.qr)
    qr=job_key(source_qr,body.test_mode,body.test_run_id)""")
    s=once(s,"    operator = body.operator.strip()","""    operator = body.operator.strip()
    actor=auth.user()
    if actor and actor['role']!='admin':operator=actor['username']""")
    s=once(s,"c.execute('''INSERT INTO flow_jobs(qr, created_at) VALUES(?,?) ON CONFLICT(qr) DO NOTHING''',\n                      (qr, utcnow()))","""c.execute('''INSERT INTO flow_jobs(qr,created_at,is_test,source_qr,test_run_id)
                         VALUES(?,?,?,?,?) ON CONFLICT(qr) DO NOTHING''',
                      (qr,utcnow(),int(body.test_mode),source_qr,body.test_run_id if body.test_mode else None))""")
    marker="            c.execute('''INSERT INTO flow_audit(attempt_id, qr, event, event_at, detail)\n                         VALUES(?,?,?,?,?)''', (sid, qr, 'started', utcnow(), station['name']))"
    s=once(s,marker,marker+"""
            previous=this.get('last_attempt_id')
            c.execute('UPDATE flow_attempts SET last_frame_at=?,rework_of=? WHERE id=?',
                      (utcnow(),previous,sid))
            if previous:auth.audit(c,'rework_started',sid,'previous attempt: '+previous)""")
    # Frame heartbeat is independent of recording uploads.
    marker="        result['visible'] = found\n        return result"
    s=once(s,marker,"""        with db.connect() as c:
            c.execute('UPDATE flow_attempts SET last_frame_at=? WHERE id=? AND ended_at IS NULL',(utcnow(),sid))
        result['visible'] = found
        return result""")
    s=once(s,"def display_attempt(row):\n    row['result']", """def display_attempt(row):
    with db.connect() as c:
        job=c.execute('SELECT source_qr,is_test,test_run_id FROM flow_jobs WHERE qr=?',(row['qr'],)).fetchone()
    row['source_qr']=job['source_qr'] if job else row['qr']
    row['test_mode']=bool(job['is_test']) if job else False
    row['test_run_id']=job['test_run_id'] if job else None
    row['result']""")
    s=once(s,"                   since: str | None = None, until: str | None = None):","                   since: str | None = None, until: str | None = None, scope: str = 'production'):")
    s=once(s,"return snapshot(q,station_id,state,operator,since,until,limit,offset)","return snapshot(q,station_id,state,operator,since,until,limit,offset,scope)")
    return s
write('production.py',production)
def cameras(s):
    s=once(s,'def open_camera(body: Open):','''def open_camera(body: Open):
    import auth
    actor=auth.user()
    if actor and actor['role']!='admin':body=body.model_copy(update={'operator':actor['username']})''')
    s=once(s,"    return {'id': body.id, 'segment_ms': 30000, 'preview_ms': 250}","""        if actor:
            c.execute('UPDATE camera_sessions SET owner_id=? WHERE id=?',(actor['id'],body.id))
    return {'id': body.id, 'segment_ms': 30000, 'preview_ms': 250}""")
    return s
write('cameras.py',cameras)
def main(s):
    s=once(s,'app.include_router(reporting_router)','''app.include_router(reporting_router)
import auth,workflows
auth.install(app)
workflows.install(app)''')
    return s
write('main.py',main)
def gateway(s):
    s=once(s,"response = await client.get('/api/flow/admin', timeout=2)","response = await client.get('/api/health', timeout=2)")
    s=once(s,"if response.status_code == 200 and 'stats' in response.json():","if response.status_code == 200 and response.json().get('ok'):")
    return s
write('mobile_gateway.py',gateway)
print('Access/workflow source changes saved. Backup:',backup)
