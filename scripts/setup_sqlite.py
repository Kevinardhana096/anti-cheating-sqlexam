"""Initialize/upgrade the score store without starting PostgreSQL or deleting exam data."""
import argparse
from contextlib import closing
import datetime
import os
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def setup(database_path, backup_directory=None):
    path = Path(database_path).resolve()
    if path.exists() and not path.is_file():
        raise ValueError('Lokasi database bukan berkas.')
    previous_version = None
    if path.is_file():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
            previous_version = conn.execute('PRAGMA user_version').fetchone()[0]
            if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise ValueError('Integritas SQLite tidak valid; setup dibatalkan.')
    path.parent.mkdir(parents=True,exist_ok=True)
    os.environ['EXAM_SQLITE_PATH'] = str(path)
    import database as db
    backup = None
    if previous_version is not None and previous_version < db.SQLITE_SCHEMA_VERSION:
        directory = Path(backup_directory or path.parent/'backups').resolve()
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        label = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = directory/f'sqlite-before-upgrade-{label}-{uuid.uuid4().hex[:8]}.db'
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(backup)) as copy:
            original.backup(copy)
            copy.execute('PRAGMA journal_mode=DELETE')
    db.init_system_db()
    with closing(db.get_sqlite_conn()) as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        count = conn.execute('SELECT COUNT(*) FROM submission_attempts').fetchone()[0]
    return {'database':str(path),'schema_version':version,'attempts':count,'backup':str(backup) if backup else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=Path(os.environ.get('EXAM_SQLITE_PATH',Path(__file__).resolve().parents[1]/'exam_system.db')))
    parser.add_argument('--backup-directory',type=Path)
    args = parser.parse_args()
    result = setup(args.database,args.backup_directory)
    print(f"SQLite siap: {result['database']}")
    print(f"Skema {result['schema_version']}; {result['attempts']} percobaan tersimpan dipertahankan.")
    if result['backup']:
        print('Backup SQLite sebelum upgrade:',result['backup'])


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print('Setup gagal:',str(error),file=sys.stderr)
        raise SystemExit(1)
