from datetime import datetime,timezone
from pathlib import Path
import sqlite3,db
destination=Path(db.DB).with_name('sopvision.pre-station-access-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.bak')
with db.connect() as source,sqlite3.connect(destination) as target:source.backup(target)
print('Consistent database backup created.')
