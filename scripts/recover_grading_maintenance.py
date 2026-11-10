"""Clear an abandoned dataset-maintenance fence only after all application/writer processes stop."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-stopped',action='store_true')
    parser.add_argument('--expected-dataset-revision',type=int,required=True)
    args = parser.parse_args()
    if not args.server_stopped:
        parser.error('Hentikan semua aplikasi/writer terlebih dahulu; gunakan --server-stopped.')
    import database as db
    import grading_queue as queue
    if not Path(os.environ.get('EXAM_SQLITE_PATH',db.SQLITE_DB_PATH)).is_file():
        raise SystemExit('Database tidak ditemukan.')
    with closing(db.get_sqlite_conn()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('PRAGMA user_version').fetchone()[0] != db.SQLITE_SCHEMA_VERSION:
            raise SystemExit('Skema database belum sesuai; periksa upgrade sebelum memulihkan fence.')
        if int(queue.setting(conn,'dataset_revision'))!=args.expected_dataset_revision:
            raise SystemExit('Revisi dataset berubah; pemulihan dibatalkan.')
        if queue.setting(conn,'exam_state','waiting')=='active':
            raise SystemExit('Status ujian masih aktif; periksa insiden sebelum menghapus fence.')
        if queue.setting(conn,'grading_maintenance',''):
            conn.execute("DELETE FROM system_settings WHERE key='grading_maintenance'")
            conn.execute("UPDATE system_settings SET value=CAST(value AS INTEGER)+1 WHERE key='dataset_revision'")
            conn.execute("UPDATE grading_jobs SET status='stale',lease_token=NULL,lease_until=NULL,version=version+1 WHERE status IN ('queued','running')")
            conn.execute("INSERT INTO exam_logs(action_type,details) VALUES('grading_maintenance_recovered','Fence dipulihkan offline; penilaian lama perlu review.')")
    print('Fence maintenance diperiksa/dipulihkan. Validasi dataset dan acuan sebelum membuka ujian.')


if __name__=='__main__':
    main()
