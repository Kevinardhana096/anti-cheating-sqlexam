"""Exercise real pg_dump/pg_restore into new database names on a disposable cluster."""
from contextlib import closing
import os
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment, postgres_bin
ensure_test_environment()
import database as db
import sandbox_roles
from exam_backup import PostgresConfig, create_backup, restore_backup, digest
import psycopg2


class PostgresBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['EXAM_TEST_ROOT'])/'recovery-test'
        cls.root.mkdir()
        cls.config = PostgresConfig(db.PG_HOST,int(db.PG_PORT),db.PG_ADMIN_USER,db.PG_ADMIN_PASS,str(postgres_bin()))
        cls.nim = 'RECOVERPG'
        ok,user,_ = db.login_student(cls.nim,'Recovered Student','testclient','backup-pg-token')
        assert ok
        cls.user = user
        cls.schema = db.init_student_sandbox_schema(cls.nim)
        result = db.execute_student_query('CREATE TABLE recovery_data(id INT GENERATED ALWAYS AS IDENTITY, label TEXT UNIQUE); INSERT INTO recovery_data(label) VALUES(\'preserved\')','sandbox_pribadi',cls.nim)
        assert result['success'],result
        cls.bundle = cls.root/'bundle'
        cls.source = Path(os.environ['EXAM_SQLITE_PATH'])
        cls.before = digest(cls.source)
        backup = create_backup(cls.source,cls.bundle,postgres=cls.config,databases=('pagila','classicmodels'))
        cls.backup_seconds = backup['elapsed_seconds']
        cls.prefix = 'recovery_'+uuid.uuid4().hex[:8]+'_'
        cls.destination = cls.root/'recovered'
        cls.result = restore_backup(cls.bundle,cls.destination,postgres=cls.config,database_prefix=cls.prefix)
        print('Recovery measurement: '+json.dumps({'backup_seconds':cls.backup_seconds,'restore_seconds':cls.result['elapsed_seconds'],'bundle_bytes':sum(p.stat().st_size for p in cls.bundle.rglob('*') if p.is_file())}),flush=True)

    @classmethod
    def tearDownClass(cls):
        from psycopg2 import sql
        with closing(db.get_pg_admin_connection('postgres')) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                for name in cls.result['postgres_databases'].values():
                    if not name.startswith(cls.prefix):
                        raise AssertionError('Refusing cleanup outside recovery fixture.')
                    cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        sandbox_roles.clear_cache()
        if not db.cleanup_student_sandbox_schema(cls.nim):
            raise AssertionError('Recovery fixture workspace cleanup failed.')

    def test_master_and_workspace_data_and_sequence_are_restored(self):
        with closing(db.get_pg_admin_connection(self.prefix+'pagila')) as conn,conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM film')
            restored_count = cursor.fetchone()[0]
            cursor.execute(f'SELECT id,label FROM {self.schema}.recovery_data')
            self.assertEqual(cursor.fetchall(),[(1,'preserved')])
        with closing(db.get_pg_admin_connection('pagila')) as conn,conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM film')
            self.assertEqual(cursor.fetchone()[0],restored_count)
        with closing(db.get_pg_admin_connection(self.prefix+'classicmodels')) as conn,conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM customers')
            self.assertGreater(cursor.fetchone()[0],0)

    def test_existing_database_is_never_overwritten(self):
        with self.assertRaisesRegex(ValueError,'sudah ada'):
            restore_backup(self.bundle,self.root/'must-not-create',postgres=self.config)
        self.assertFalse((self.root/'must-not-create').exists())

    def test_role_access_rebuilt_from_preserved_secret(self):
        restored_sqlite = self.destination/'exam_system.db'
        original_connection = db.get_pg_admin_connection
        restored_name = self.prefix+'pagila'
        with patch.dict(os.environ,{'EXAM_SQLITE_PATH':str(restored_sqlite)}),patch.object(db,'DEFAULT_EXAM_DB',restored_name),patch.object(db,'get_pg_admin_connection',side_effect=lambda dbname=None:original_connection(dbname or restored_name)):
            sandbox_roles.clear_cache()
            schema,role,password = sandbox_roles.ensure_workspace(self.nim)
            with closing(psycopg2.connect(host=db.PG_HOST,port=db.PG_PORT,user=role,password=password,dbname=self.prefix+'pagila')) as conn,conn.cursor() as cursor:
                cursor.execute(f'SELECT label FROM {schema}.recovery_data')
                self.assertEqual(cursor.fetchone()[0],'preserved')
                cursor.execute(f"INSERT INTO {schema}.recovery_data(label) VALUES('after restore') RETURNING id")
                self.assertEqual(cursor.fetchone()[0],2)
            sandbox_roles.clear_cache()

    def test_source_sqlite_is_unchanged_and_restore_revokes_sessions(self):
        self.assertEqual(digest(self.source),self.before)
        with closing(sqlite3.connect(self.destination/'exam_system.db')) as conn:
            self.assertIsNone(conn.execute('SELECT session_token FROM users WHERE id=?',(self.user['id'],)).fetchone()[0])
        self.assertTrue(self.result['postgres_restored'])


if __name__=='__main__':
    unittest.main(verbosity=2)
