"""Refuse a busy deployment and take a consistent backup without initializing DB."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import db

ROOT = Path(__file__).resolve().parent


def prepare():
    with db.connect() as c:
        work = c.execute('SELECT count(*) FROM flow_attempts WHERE ended_at IS NULL').fetchone()[0]
        cameras = c.execute("""SELECT count(*) FROM camera_sessions WHERE state='open'
            AND julianday(last_seen)>julianday('now','-45 seconds')""").fetchone()[0]
        archives=c.execute("""SELECT count(*) FROM flow_attempts WHERE state='passed'
          AND json_extract(result_json,'$.recording_pending')=1
          AND julianday(updated_at)>julianday('now','-10 minutes')""").fetchone()[0]
        if work or cameras or archives:
            raise SystemExit(f'Update deferred: {work} unfinished jobs, {cameras} online cameras, {archives} pending videos. No server stopped.')
        folder = ROOT / 'backups' / ('stability-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        folder.mkdir(parents=True)
        with sqlite3.connect(folder / 'sopvision.db') as target:
            c.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed; no server stopped')
        counts = {table:c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('flow_jobs', 'flow_attempts', 'reports', 'camera_sessions', 'camera_segments', 'users')}
        (folder / 'counts.json').write_text(json.dumps(counts, indent=2), encoding='utf-8')
    print('Idle confirmed. Consistent verified backup:', folder)


if __name__ == '__main__':
    prepare()
