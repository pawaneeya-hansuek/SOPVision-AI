import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

DB = Path(__file__).with_name('sopvision.db')
DEFAULT_STEPS = [
    ('วางฐานงานสีเขียว', 'green', 1.0),
    ('ติดตั้งชิ้นส่วนสีแดง', 'red', 0.45),
    ('ติดตั้งชิ้นส่วนสีน้ำเงิน', 'blue', 0.45),
    ('ติดตั้งชิ้นส่วนสีเหลือง', 'yellow', 0.45),
]


def backup_before_schema_change():
    if not DB.exists():
        return
    with sqlite3.connect(DB) as source:
        tables = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables or 'station_configs' in tables:
            return
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = DB.with_name(f'{DB.stem}.pre-roi-{stamp}.bak')
        with sqlite3.connect(backup) as destination:
            source.backup(destination)


def backup_before_traceability_change():
    if not DB.exists():
        return
    with sqlite3.connect(DB) as source:
        tables = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables or 'reports' not in tables or 'camera_sessions' not in tables:
            return
        report_columns = {row[1] for row in source.execute('PRAGMA table_info(reports)')}
        links_exist = 'camera_work_links' in tables
        if {'qr', 'attempt_id', 'station_id'} <= report_columns and links_exist:
            return
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = DB.with_name(f'{DB.stem}.pre-traceability-{stamp}.bak')
        with sqlite3.connect(backup) as destination:
            source.backup(destination)


@contextmanager
def connect():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    # Readers (admin/live status) must not block durable camera/job writes.
    # FULL synchronization remains SQLite's default for every connection.
    with sqlite3.connect(DB, timeout=15) as configuration:
        configuration.execute('PRAGMA journal_mode=WAL')
    if DB.exists():
        with sqlite3.connect(DB) as source:
            names={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if names and 'users' not in names:
                stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                with sqlite3.connect(DB.with_name(DB.stem+'.pre-access-'+stamp+'.bak')) as target:
                    source.backup(target)
    backup_before_schema_change()
    backup_before_traceability_change()
    with connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY, position INTEGER NOT NULL, name TEXT NOT NULL,
            color TEXT NOT NULL UNIQUE, min_pct REAL NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, mode TEXT NOT NULL, created_at TEXT NOT NULL,
            duration REAL, status TEXT NOT NULL, verified INTEGER NOT NULL,
            total INTEGER NOT NULL, issues INTEGER NOT NULL, result_json TEXT NOT NULL,
            video_url TEXT DEFAULT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS flow_jobs (
            qr TEXT PRIMARY KEY, created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS station_configs (
            station_id INTEGER PRIMARY KEY, version INTEGER NOT NULL,
            config_json TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS flow_attempts (
            id TEXT PRIMARY KEY, qr TEXT NOT NULL REFERENCES flow_jobs(qr),
            station_id INTEGER NOT NULL, operator TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('active','passed','blocked','interrupted')),
            started_at TEXT NOT NULL, ended_at TEXT,
            video_url TEXT, result_json TEXT)''')
        c.execute('''CREATE INDEX IF NOT EXISTS flow_attempts_qr_idx
                    ON flow_attempts(qr, station_id)''')
        columns = {r['name'] for r in c.execute('PRAGMA table_info(flow_attempts)')}
        for name, definition in {
            'request_id': 'TEXT', 'station_json': 'TEXT', 'mime_type': 'TEXT',
            'updated_at': 'TEXT', 'recorded_bytes': 'INTEGER NOT NULL DEFAULT 0',
            'recorded_chunks': 'INTEGER NOT NULL DEFAULT 0', 'frame_url': 'TEXT',
        }.items():
            if name not in columns:
                c.execute(f'ALTER TABLE flow_attempts ADD COLUMN {name} {definition}')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS flow_request_idx ON flow_attempts(request_id) WHERE request_id IS NOT NULL')
        c.execute('''CREATE TABLE IF NOT EXISTS flow_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id TEXT NOT NULL, qr TEXT NOT NULL,
            event TEXT NOT NULL, event_at TEXT NOT NULL, detail TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS camera_sessions (
            id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, source TEXT NOT NULL,
            station_id INTEGER, operator TEXT NOT NULL, device_label TEXT NOT NULL,
            mime_type TEXT NOT NULL, started_at TEXT NOT NULL, last_seen TEXT NOT NULL,
            ended_at TEXT, state TEXT NOT NULL, frame_sequence INTEGER NOT NULL DEFAULT -1,
            frame_hash TEXT, frame_at TEXT, error TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS camera_segments (
            camera_id TEXT NOT NULL REFERENCES camera_sessions(id), segment_index INTEGER NOT NULL,
            started_at TEXT NOT NULL, ended_at TEXT, state TEXT NOT NULL,
            chunks INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(camera_id, segment_index))''')
        c.execute('''CREATE TABLE IF NOT EXISTS camera_chunks (
            camera_id TEXT NOT NULL, segment_index INTEGER NOT NULL, sequence INTEGER NOT NULL,
            digest TEXT NOT NULL, size INTEGER NOT NULL,
            PRIMARY KEY(camera_id,segment_index,sequence),
            FOREIGN KEY(camera_id,segment_index) REFERENCES camera_segments(camera_id,segment_index))''')
        report_columns = {r['name'] for r in c.execute('PRAGMA table_info(reports)')}
        if 'qr' not in report_columns:
            c.execute('ALTER TABLE reports ADD COLUMN qr TEXT REFERENCES flow_jobs(qr)')
        if 'attempt_id' not in report_columns:
            c.execute('ALTER TABLE reports ADD COLUMN attempt_id TEXT REFERENCES flow_attempts(id)')
        if 'station_id' not in report_columns:
            c.execute('ALTER TABLE reports ADD COLUMN station_id INTEGER')
        c.execute('''CREATE TABLE IF NOT EXISTS camera_work_links (
            camera_id TEXT NOT NULL REFERENCES camera_sessions(id),
            qr TEXT NOT NULL REFERENCES flow_jobs(qr),
            attempt_id TEXT NOT NULL REFERENCES flow_attempts(id),
            linked_at TEXT NOT NULL, unlinked_at TEXT,
            PRIMARY KEY(camera_id, attempt_id))''')
        c.execute('CREATE INDEX IF NOT EXISTS camera_work_links_qr_idx ON camera_work_links(qr)')
        c.execute('CREATE INDEX IF NOT EXISTS reports_qr_idx ON reports(qr, created_at)')
        c.execute('CREATE INDEX IF NOT EXISTS camera_segments_time_idx ON camera_segments(started_at)')
        c.execute("UPDATE camera_sessions SET state='interrupted', ended_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), error='เซิร์ฟเวอร์เริ่มใหม่' WHERE state='open'")
        c.execute("UPDATE camera_segments SET state='partial', ended_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE state='recording'")
        c.execute("UPDATE camera_work_links SET unlinked_at=coalesce((SELECT ended_at FROM camera_sessions s WHERE s.id=camera_id),strftime('%Y-%m-%dT%H:%M:%SZ','now')) WHERE unlinked_at IS NULL")
        import auth,workflows
        auth.initialize_schema(c)
        workflows.initialize_schema(c)
        # Only the single production backend calls initialize; the mobile gateway does not.
        ended = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for row in c.execute("SELECT * FROM flow_attempts WHERE ended_at IS NULL AND state IN ('active','blocked')").fetchall():
            result = json.loads(row['result_json'] or '{}')
            result['status'] = 'review'
            result['error'] = 'เซิร์ฟเวอร์หยุดระหว่างทำงาน ต้องแยกชิ้นงานเพื่อตรวจสอบ'
            for step in result.get('steps', []):
                if step.get('status') == 'pending':
                    step['status'] = 'missing'
            result['issues'] = max(1, sum(s.get('status') != 'passed' for s in result.get('steps', [])))
            state = 'blocked' if row['state'] == 'blocked' else 'interrupted'
            c.execute('''UPDATE flow_attempts SET state=?, ended_at=?, updated_at=?, result_json=?
                         WHERE id=? AND ended_at IS NULL''',
                      (state, ended, ended, json.dumps(result, ensure_ascii=False), row['id']))
            c.execute('''INSERT INTO flow_audit(attempt_id, qr, event, event_at, detail)
                         VALUES(?,?,?,?,?)''', (row['id'], row['qr'], 'server_interrupted', ended, result['error']))
        if not c.execute('SELECT count(*) FROM steps').fetchone()[0]:
            c.executemany('INSERT INTO steps(position,name,color,min_pct) VALUES (?,?,?,?)',
                          [(i,*row) for i,row in enumerate(DEFAULT_STEPS)])


def steps():
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM steps ORDER BY position')]


def load_station_config(station_id):
    with connect() as c:
        row = c.execute('''SELECT version, config_json FROM station_configs
                           WHERE station_id=?''', (station_id,)).fetchone()
    if row is None:
        return None
    return {'version': row['version'], **json.loads(row['config_json'])}


def save_station_config(station_id, config, expected_version):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT version FROM station_configs WHERE station_id=?',
                        (station_id,)).fetchone()
        current_version = row['version'] if row else 0
        if current_version != expected_version:
            return None
        version = current_version + 1
        c.execute('''INSERT INTO station_configs(station_id, version, config_json, updated_at)
                     VALUES(?,?,?,?)
                     ON CONFLICT(station_id) DO UPDATE SET version=excluded.version,
                       config_json=excluded.config_json, updated_at=excluded.updated_at''',
                  (station_id, version, json.dumps(config, ensure_ascii=False),
                   datetime.now(timezone.utc).isoformat(timespec='seconds')))
    return {'version': version, **config}


def replace_steps(rows):
    with connect() as c:
        c.execute('DELETE FROM steps')
        c.executemany('INSERT INTO steps(position,name,color,min_pct) VALUES (?,?,?,?)',
                      [(i,r['name'],r['color'],r['min_pct']) for i,r in enumerate(rows)])
    return steps()


def save_report(id, mode, created_at, result, video_url=None, qr=None, attempt_id=None,
                station_id=None):
    with connect() as c:
        if qr:
            job = c.execute('SELECT qr FROM flow_jobs WHERE qr=?', (qr,)).fetchone()
            if job is None:
                raise ValueError('ไม่พบ QR งานในระบบ จึงเชื่อมรายงานไม่ได้')
        if attempt_id:
            attempt = c.execute('SELECT qr,station_id FROM flow_attempts WHERE id=?',
                                (attempt_id,)).fetchone()
            if (attempt is None or attempt['qr'] != qr
                    or (station_id is not None and attempt['station_id'] != station_id)):
                raise ValueError('รหัสรอบงานไม่ตรงกับ QR ที่ระบุ')
        c.execute('''INSERT OR REPLACE INTO reports
          (id,mode,created_at,duration,status,verified,total,issues,result_json,video_url,qr,attempt_id,station_id)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (id,mode,created_at,result['elapsed'],result['status'],result['verified'],
           result['total'],result['issues'],json.dumps(result,ensure_ascii=False),video_url,
           qr,attempt_id,station_id))


def get_reports(limit=100):
    with connect() as c:
        return [dict(r) for r in c.execute('''SELECT id,mode,created_at,duration,status,verified,total,issues,video_url,qr,attempt_id,station_id
                  FROM reports ORDER BY created_at DESC LIMIT ?''',(limit,))]


def get_report(id):
    with connect() as c:
        r = c.execute('SELECT * FROM reports WHERE id=?',(id,)).fetchone()
    if r is None: return None
    d = dict(r); d['result'] = json.loads(d.pop('result_json')); return d


def get_traceability(qr):
    with connect() as c:
        job = c.execute('SELECT qr,created_at FROM flow_jobs WHERE qr=?', (qr,)).fetchone()
        if job is None:
            return None
        attempts = [dict(row) for row in c.execute(
            'SELECT * FROM flow_attempts WHERE qr=? ORDER BY started_at,station_id', (qr,))]
        reports = [dict(row) for row in c.execute(
            'SELECT * FROM reports WHERE qr=? ORDER BY created_at', (qr,))]
        links = [dict(row) for row in c.execute('''SELECT l.*,s.source,s.station_id,s.operator,
                    s.device_label,s.mime_type,s.state camera_state,s.started_at camera_started_at,
                    s.ended_at camera_ended_at,s.error camera_error
                    FROM camera_work_links l JOIN camera_sessions s ON s.id=l.camera_id
                    WHERE l.qr=? ORDER BY l.linked_at''', (qr,))]
        for link in links:
            segments = [dict(row) for row in c.execute('''SELECT * FROM camera_segments
                WHERE camera_id=? AND started_at<=coalesce(?, '9999')
                AND coalesce(ended_at, '9999')>=? ORDER BY segment_index''',
                (link['camera_id'], link['unlinked_at'], link['linked_at']))]
            for segment in segments:
                path = Path(__file__).resolve().parent / 'media' / 'cameras' / (
                    f"{link['camera_id']}_{segment['segment_index']}"
                    f"{'.mp4' if link['mime_type'].startswith('video/mp4') else '.webm'}")
                segment['available'] = segment['state'] != 'recording' and segment['bytes'] > 0 and path.is_file()
                segment['video_url'] = (
                    f"/api/cameras/{link['camera_id']}/segments/{segment['segment_index']}/video"
                    if segment['available'] else None)
            link['segments'] = segments
        for attempt in attempts:
            attempt['result'] = json.loads(attempt.pop('result_json') or '{}')
        for report in reports:
            report['result'] = json.loads(report.pop('result_json'))
    return {
        'job': dict(job),
        'attempts': attempts,
        'reports': reports,
        'camera_links': links,
        'legacy_note': 'ข้อมูลเดิมที่ไม่มี QR/รอบงานอ้างอิงจะไม่ถูกจับคู่โดยคาดเดา',
    }


def stats():
    with connect() as c:
        overall = c.execute('''SELECT count(*) total, sum(status='pass') passed,
                          sum(status='review') review, sum(mode='live') live
                          FROM reports''').fetchone()
    o = dict(overall)
    o = {k: int(v or 0) for k,v in o.items()}
    o['rate'] = round(100*o['passed']/o['total']) if o['total'] else 0
    return o
