"""Backup, verify, or recover an exam into new destinations; never overwrite live data."""
import argparse
import os
from pathlib import Path
import sys

# The CLI and implementation have the same basename; resolve the root implementation first.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exam_backup import PostgresConfig, create_backup, verify_backup, restore_backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup','verify','restore'])
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--sqlite', type=Path)
    parser.add_argument('--uploads', type=Path)
    parser.add_argument('--pg-bin', default=os.environ.get('PG_BIN',''))
    parser.add_argument('--database-prefix', default='')
    parser.add_argument('--sqlite-only', action='store_true')
    parser.add_argument('--server-stopped', action='store_true')
    args = parser.parse_args()
    if args.action == 'verify':
        result = verify_backup(args.bundle)
        print(f"Backup valid: {len(result['files'])} berkas, skema SQLite {result['sqlite_version']}.")
        return 0
    if not args.server_stopped:
        parser.error('Hentikan aplikasi dan writer lain, lalu gunakan --server-stopped.')
    import database as db
    config = None if args.sqlite_only else PostgresConfig(db.PG_HOST,int(db.PG_PORT),db.PG_ADMIN_USER,db.PG_ADMIN_PASS,args.pg_bin)
    if args.action == 'backup':
        sqlite = args.sqlite or Path(os.environ.get('EXAM_SQLITE_PATH',db.SQLITE_DB_PATH))
        uploads = args.uploads or Path(db.BASE_DIR)/'static/uploads/questions'
        create_backup(sqlite,args.bundle,uploads=uploads,postgres=config,
                      databases=() if args.sqlite_only else tuple(sorted(db.ALLOWED_MASTER_DBS)))
        print('Backup selesai; simpan direktori ini sebagai data rahasia.')
    else:
        if args.destination is None:
            parser.error('--destination diperlukan untuk restore.')
        result = restore_backup(args.bundle,args.destination,postgres=config,database_prefix=args.database_prefix,sqlite_only=args.sqlite_only)
        print('Pemulihan selesai ke direktori/database baru; sesi dicabut dan ujian menunggu pengawas.')
        print('PostgreSQL dipulihkan:',result['postgres_restored'])
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Operasi gagal: {error}',file=sys.stderr)
        raise SystemExit(1)
