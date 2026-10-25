"""Archive trial records/media and reset operational data; backend must be stopped."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    'camera_chunks', 'camera_work_links', 'camera_segments', 'camera_sessions',
    'supervisor_reviews', 'reports', 'flow_audit', 'flow_attempts', 'flow_jobs', 'test_runs',
)
MEDIA = ('cameras', 'evidence', 'playback', 'recordings', 'uploads')


def fingerprint(connection, table):
    rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    database = ROOT / 'sopvision.db'
    connection = sqlite3.connect(database, timeout=15)
    connection.execute('PRAGMA foreign_keys=ON')
    counts = {table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
              for table in TABLES}
    if not args.apply:
        print(json.dumps({'preview': counts}))
        connection.close()
        return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8000)) == 0:
            raise RuntimeError('Stop the backend before applying this reset')
    if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise RuntimeError('Database integrity check failed; nothing reset')
    if connection.execute('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Foreign key check failed; nothing reset')
    names = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    preserved = {name: fingerprint(connection, name)
                 for name in names - set(TABLES) - {'sqlite_sequence'}}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = ROOT / 'backups' / ('reset-' + stamp)
    backup.mkdir(parents=True)
    with sqlite3.connect(backup / 'sopvision.db') as destination:
        connection.backup(destination)
    manifest = {'created_at': stamp, 'before': counts, 'preserved': preserved,
                'media': list(MEDIA), 'status': 'backed_up'}
    manifest_path = backup / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    moved = []
    committed = False
    try:
        connection.execute('BEGIN IMMEDIATE')
        for name in MEDIA:
            source = (ROOT / 'media' / name).resolve()
            destination = (backup / 'media' / name).resolve()
            if not source.is_relative_to(ROOT / 'media') or not destination.is_relative_to(backup):
                raise RuntimeError('Unsafe media path')
            if source.exists():
                if source.is_symlink() or source.is_junction():
                    raise RuntimeError('Media directory is a link; refusing reset')
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
                moved.append((source, destination))
                source.mkdir()
                if (destination / '.gitkeep').exists():
                    (source / '.gitkeep').touch()
        for table in TABLES:
            connection.execute(f'DELETE FROM "{table}"')
        connection.execute("DELETE FROM sqlite_sequence WHERE name='flow_audit'")
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Reset produced invalid foreign keys')
        for table, digest in preserved.items():
            if fingerprint(connection, table) != digest:
                raise RuntimeError('Preserved data changed: ' + table)
        assert all(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0
                   for table in TABLES)
        connection.commit()
        committed = True
        manifest['status'] = 'complete'
        manifest['after'] = {table: 0 for table in TABLES}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps({'backup': str(backup), 'before': counts, 'after': manifest['after']}))
    except BaseException:
        if not committed:
            connection.rollback()
            for source, destination in reversed(moved):
                marker = source / '.gitkeep'
                if marker.exists():
                    marker.unlink()
                source.rmdir()
                shutil.move(str(destination), str(source))
        raise
    finally:
        connection.close()


if __name__ == '__main__':
    main()
