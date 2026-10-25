"""Prevent a second backend from recovering a database that is still in use."""
import os
from pathlib import Path


class BackendGuard:
    def __init__(self, database):
        self.path = Path(str(database) + '.runtime.lock')
        self.handle = None

    def __enter__(self):
        handle = self.path.open('a+b')
        try:
            if handle.seek(0, 2) == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError('SOPVision backend already uses this database. Use the existing server.') from exc
        self.handle = handle
        return self

    def __exit__(self, *args):
        if self.handle is not None:
            # Closing also releases the OS lock after a crash; never delete the
            # lock file (another process may already have opened its inode).
            self.handle.close()
            self.handle = None
