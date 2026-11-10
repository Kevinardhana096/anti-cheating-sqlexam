"""Recovery refuses overwrite, checks all hashes, and preserves history while revoking sessions."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database as db
import admin_security
from exam_backup import create_backup, verify_backup, restore_backup, digest


class BackupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='sqlexam_backup_')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ,{'EXAM_SQLITE_PATH':str(self.root/'source.db'),'ADMIN_MASTER_KEY':'backup-test-key-123'})
        env.start()
        self.addCleanup(env.stop)
        db.init_system_db()
        self.source = self.root/'source.db'
        self.bundle = self.root/'bundle'
        self.restored = self.root/'restored'
        ok,self.user,_ = db.login_student('BACKUP01','Recovery Student','testclient','recovery-token')
        self.assertTrue(ok)
        self.qid = db.get_all_questions()[0]['id']
        db.save_submission(self.user['id'],self.qid,'SELECT 1',1,10,'correct','Saved')
        db.save_submission(self.user['id'],self.qid,'SELECT 2',0,0,'wrong_data','Incorrect')
        admin_security.create_session('testclient')
        db.set_exam_state('active')

    def test_roundtrip_preserves_best_history_secrets_and_revokes_sessions(self):
        before = digest(self.source)
        create_backup(self.source,self.bundle)
        self.assertEqual(verify_backup(self.bundle)['sqlite_version'],db.SQLITE_SCHEMA_VERSION)
        result = restore_backup(self.bundle,self.restored)
        self.assertFalse(result['postgres_restored'])
        with closing(sqlite3.connect(self.restored/'exam_system.db')) as conn:
            self.assertEqual(conn.execute('SELECT score,submitted_query FROM submissions').fetchone(),(10,'SELECT 1'))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM submission_attempts').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM admin_sessions').fetchone()[0],0)
            self.assertIsNone(conn.execute('SELECT session_token FROM users').fetchone()[0])
            self.assertEqual(conn.execute("SELECT value FROM system_settings WHERE key='exam_state'").fetchone()[0],'waiting')
            self.assertTrue(admin_security.check_key('backup-test-key-123',conn.execute("SELECT value FROM system_settings WHERE key='admin_master_key'").fetchone()[0]))
        self.assertEqual(digest(self.source),before)

    def test_sqlite_backup_includes_wal_not_only_main_file(self):
        with closing(db.get_sqlite_conn()) as conn, conn:
            conn.execute("UPDATE users SET name='Committed in WAL'")
            conn.commit()
            self.assertTrue(Path(str(self.source)+'-wal').exists())
            create_backup(self.source,self.bundle)
        with closing(sqlite3.connect(self.bundle/'exam_system.db')) as conn:
            self.assertEqual(conn.execute('SELECT name FROM users').fetchone()[0],'Committed in WAL')

    def test_uploads_included_and_environment_not_included(self):
        uploads = self.root/'uploads'
        uploads.mkdir()
        (uploads/'fixture.png').write_bytes(b'image fixture')
        (self.root/'.env').write_text('not-for-backup')
        create_backup(self.source,self.bundle,uploads=uploads)
        restore_backup(self.bundle,self.restored)
        self.assertEqual((self.restored/'static/uploads/questions/fixture.png').read_bytes(),b'image fixture')
        self.assertFalse((self.bundle/'.env').exists())

    def test_corrupt_file_rejected_before_destination_created(self):
        create_backup(self.source,self.bundle)
        with (self.bundle/'exam_system.db').open('ab') as output:
            output.write(b'corrupt')
        with self.assertRaisesRegex(ValueError,'Checksum'):
            restore_backup(self.bundle,self.restored)
        self.assertFalse(self.restored.exists())

    def test_backup_and_restore_refuse_existing_destinations(self):
        create_backup(self.source,self.bundle)
        before = digest(self.bundle/'exam_system.db')
        with self.assertRaises(ValueError):
            create_backup(self.source,self.bundle)
        self.restored.mkdir()
        marker = self.restored/'keep.txt'
        marker.write_text('keep')
        with self.assertRaises(ValueError):
            restore_backup(self.bundle,self.restored)
        self.assertEqual(marker.read_text(),'keep')
        self.assertEqual(digest(self.bundle/'exam_system.db'),before)

    def test_manifest_traversal_and_windows_paths_are_rejected(self):
        create_backup(self.source,self.bundle)
        manifest = json.loads((self.bundle/'manifest.json').read_text())
        for unsafe in ('../outside','C:/outside','static\\uploads\\questions\\x'):
            modified = {**manifest,'files':{**manifest['files'],unsafe:{'sha256':'x','bytes':0}}}
            (self.bundle/'manifest.json').write_text(json.dumps(modified))
            with self.subTest(unsafe=unsafe),self.assertRaises(ValueError):
                verify_backup(self.bundle)

    def test_missing_dump_is_not_a_full_backup(self):
        create_backup(self.source,self.bundle)
        manifest = json.loads((self.bundle/'manifest.json').read_text())
        manifest['databases'] = ['pagila']
        (self.bundle/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'Dump PostgreSQL'):
            verify_backup(self.bundle)

    def test_failed_dump_never_publishes_successful_backup(self):
        from exam_backup import PostgresConfig
        with patch('exam_backup.pg_command',side_effect=RuntimeError('failed')),patch.object(PostgresConfig,'tool',return_value='pg_dump'):
            with self.assertRaises(RuntimeError):
                create_backup(self.source,self.bundle,postgres=PostgresConfig('localhost',1,'test'),databases=('pagila',))
        self.assertFalse(self.bundle.exists())
        self.assertEqual(len(list(self.root.glob('bundle.incomplete-*'))),1)

    def test_unknown_schema_version_is_rejected(self):
        with closing(db.get_sqlite_conn()) as conn, conn:
            conn.execute('PRAGMA user_version=999')
        with self.assertRaisesRegex(ValueError,'Versi skema'):
            create_backup(self.source,self.bundle)

    def test_backup_inside_uploads_is_rejected(self):
        uploads = self.root/'uploads'
        uploads.mkdir()
        with self.assertRaises(ValueError):
            create_backup(self.source,uploads/'backup',uploads=uploads)


if __name__=='__main__':
    unittest.main(verbosity=2)
