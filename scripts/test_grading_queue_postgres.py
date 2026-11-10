"""Real evaluator/worker integration on a disposable PostgreSQL cluster."""
from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment
ensure_test_environment()
import database as db
import grading_queue as queue
import main
from fastapi.testclient import TestClient


class QueuePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.set_exam_state('waiting')
        db.create_package('QUEUEPG','Queue PostgreSQL','Queue fixtures',1)
        cls.master = db.save_question(1,'Master queue','Compare complete rows',10,
                    'SELECT n FROM generate_series(1,1000) n',category='QUEUEPG',target_database='pagila')
        cls.sandbox = db.save_question(2,'Sandbox queue','Explicit setup',10,'SELECT id FROM basis',
                    category='QUEUEPG',target_database='sandbox_pribadi',setup_query='CREATE TABLE basis(id INT); INSERT INTO basis VALUES(7)')
        ok,cls.user,_ = db.login_student('QUEUEPG01','Queue PG Student','testclient','queue-pg-token')
        assert ok
        db.lock_student_category('QUEUEPG01','QUEUEPG')

    def setUp(self):
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('DELETE FROM submissions WHERE user_id=?',(self.user['id'],))
            conn.execute('DELETE FROM submission_attempts WHERE user_id=?',(self.user['id'],))
        db.set_exam_state('active')

    def pending(self, qid=None, query='SELECT n FROM generate_series(1,1000) n'):
        return db.save_submission(self.user['id'],qid or self.master,query,None,None,'evaluation_limit','Pending',graded=False)

    def test_real_grading_after_stop_without_resubmission(self):
        self.pending()
        db.set_exam_state('finished')
        with closing(TestClient(main.app,follow_redirects=False)) as access_client:
            access_client.cookies.set('student_nim','QUEUEPG01')
            access_client.cookies.set('student_token','queue-pg-token')
            self.assertEqual(access_client.get('/api/student/questions').status_code,403)
        self.assertTrue(queue.Worker().run_once())
        best = db.get_student_submissions(self.user['id'])[self.master]
        self.assertEqual(best['score'],10)
        self.assertEqual(best['latest_attempt']['graded'],1)
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM submission_attempts').fetchone()[0],1)
            self.assertIsNone(conn.execute('SELECT score FROM submission_attempts').fetchone()[0])

    def test_real_wrong_answer_is_zero_after_evaluation_not_pending(self):
        self.pending(query='SELECT n FROM generate_series(1,999) n')
        queue.Worker().run_once()
        best = db.get_student_submissions(self.user['id'])[self.master]
        self.assertEqual(best['score'],0)
        self.assertEqual(best['latest_attempt']['graded'],1)
        self.assertEqual(best['latest_attempt']['eval_status'],'row_count_mismatch')

    def test_sandbox_setup_replay_does_not_create_live_workspace(self):
        self.pending(self.sandbox,'SELECT id FROM basis')
        queue.Worker().run_once()
        best = db.get_student_submissions(self.user['id'])[self.sandbox]
        self.assertEqual(best['score'],10)
        with closing(db.get_pg_admin_connection()) as conn,conn.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',(db.get_clean_student_schema_name('QUEUEPG01'),))
            self.assertIsNone(cursor.fetchone())

    def test_lifespan_starts_worker_and_joins_before_closing_pool(self):
        self.pending()
        with TestClient(main.app):
            deadline = time.monotonic()+15
            while time.monotonic()<deadline:
                with closing(db.get_sqlite_conn()) as conn:
                    if conn.execute("SELECT COUNT(*) FROM grading_jobs WHERE status='completed'").fetchone()[0]:
                        break
                time.sleep(.1)
            else:
                self.fail('Startup worker did not complete accepted work')
        self.assertFalse(main.app.state.grading_worker.thread.is_alive())
        self.assertEqual(db.get_student_submissions(self.user['id'])[self.master]['score'],10)

    def test_persisted_claim_is_recovered_after_process_exit(self):
        self.pending()
        result = subprocess.run([sys.executable,'-c',"import grading_queue; assert grading_queue.claim()['job']"],
                                cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('UPDATE grading_jobs SET lease_until=0')
        queue.Worker().run_once()
        self.assertEqual(db.get_student_submissions(self.user['id'])[self.master]['score'],10)

    def test_missing_master_data_pauses_exam_before_reseed(self):
        db.set_exam_state('finished')
        self.assertTrue(db.empty_target_database('classicmodels')[0])
        db.set_exam_state('active')
        self.pending()
        ok,message = db.init_postgres_db()
        self.assertTrue(ok,message)
        self.assertEqual(db.get_exam_state(),'waiting')
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute('SELECT status FROM grading_jobs').fetchone()[0],'stale')
        with closing(db.get_pg_admin_connection('classicmodels')) as conn,conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM customers')
            self.assertGreater(cursor.fetchone()[0],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
