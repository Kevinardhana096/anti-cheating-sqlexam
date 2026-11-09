"""Deterministic start-of-exam races and lost-response recovery on temporary SQLite."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import threading
import unittest
from unittest.mock import patch
import psycopg2
from fastapi.testclient import TestClient
import test_exam_access as access_tests
from admin_test_support import authenticate_admin
import database as db
import main


class StartFailureTests(unittest.TestCase):
    setUp = access_tests.ExamAccessTests.setUp
    submission_count = access_tests.ExamAccessTests.submission_count

    def admin(self):
        client = TestClient(main.app)
        self.addCleanup(client.close)
        authenticate_admin(client)
        return client

    def test_stop_wins_against_start_still_validating(self):
        db.set_exam_state('waiting')
        second = self.admin()
        entered, release = threading.Event(), threading.Event()
        def validate(*args):
            entered.set()
            if not release.wait(10):
                raise TimeoutError('Test synchronization failed')
            return {'status':'valid'}
        with patch('grading_engine.validate_reference', side_effect=validate), ThreadPoolExecutor(2) as pool:
            pending = pool.submit(self.client.post, '/api/admin/exam/start')
            try:
                self.assertTrue(entered.wait(10))
                self.assertEqual(second.post('/api/admin/exam/stop').status_code, 200)
            finally:
                release.set()
            self.assertEqual(pending.result(10).status_code, 400)
        self.assertEqual(db.get_exam_state(), 'finished')

    def test_two_starts_commit_one_transition(self):
        db.set_exam_state('waiting')
        second = self.admin()
        barrier = threading.Barrier(2)
        local = threading.local()
        def validate(*args):
            if not getattr(local, 'entered', False):
                local.entered = True
                barrier.wait(10)
            return {'status':'valid'}
        with patch('grading_engine.validate_reference', side_effect=validate), ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(c.post, '/api/admin/exam/start') for c in (self.client, second)]
            self.assertEqual(sorted(f.result(15).status_code for f in futures), [200,400])
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM exam_logs WHERE action_type='exam_started'").fetchone()[0], 2)  # fixture start plus this transition
        self.assertEqual(db.get_exam_state(), 'active')

    def test_postgres_disconnect_during_validation_never_opens_exam(self):
        db.set_exam_state('waiting')
        with patch('grading_engine.validate_reference', side_effect=psycopg2.OperationalError('connection lost')):
            self.assertEqual(self.client.post('/api/admin/exam/start').status_code,400)
        self.assertEqual(db.get_exam_state(),'waiting')
        self.assertEqual(self.client.get('/api/student/questions').status_code,403)

    def test_crash_between_validation_and_commit_leaves_waiting(self):
        db.set_exam_state('waiting')
        class SimulatedProcessExit(BaseException):
            pass
        with patch('grading_engine.validate_reference', side_effect=SimulatedProcessExit):
            with self.assertRaises(SimulatedProcessExit):
                db.start_exam_validated()
        self.assertEqual(db.get_exam_state(),'waiting')
        with patch('grading_engine.validate_reference',return_value={'status':'valid'}):
            db.start_exam_validated()
        self.assertEqual(db.get_exam_state(),'active')

    def test_twenty_four_waiting_students_enter_and_lock_concurrently(self):
        db.set_exam_state('waiting')
        clients=[]
        for n in range(24):
            c=TestClient(main.app)
            self.addCleanup(c.close)
            r=c.post('/login',data={'nim':f'BURST{n:02}','name':f'Burst {n}','device_id':f'burst-{n}'},follow_redirects=False)
            self.assertEqual(r.status_code,302)
            self.assertEqual(c.get('/api/exam/state').json()['state'],'waiting')
            clients.append(c)
        with patch('grading_engine.validate_reference',return_value={'status':'valid'}):
            self.assertEqual(self.client.post('/api/admin/exam/start').status_code,200)
        def enter(c):
            self.assertEqual(c.get('/api/exam/state').json()['state'],'active')
            self.assertEqual(c.get('/exam',follow_redirects=False).status_code,200)
            self.assertEqual(c.post('/api/student/select-category',json={'nim':c.cookies.get('student_nim'),'session_token':c.cookies.get('student_token'),'category':'A'}).status_code,200)
            self.assertEqual(c.get('/api/student/questions').status_code,200)
        with ThreadPoolExecutor(24) as pool:
            list(pool.map(enter,clients))

    def test_lost_package_response_retry_recovers_same_lock(self):
        db.reset_student_category('ACCESS01')
        payload={**self.payload,'category':'A'}
        self.client.post('/api/student/select-category',json=payload)  # response discarded
        r=self.client.post('/api/student/select-category',json=payload)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['category'],'A')
        self.assertEqual(self.client.get('/api/student/questions').json()['category'],'A')

    def test_failure_after_state_update_rolls_back_transition(self):
        db.set_exam_state('waiting')
        original=db._set_exam_state
        def fail(conn,state):
            original(conn,state)
            raise RuntimeError('Injected failure before transaction commit')
        with patch('grading_engine.validate_reference',return_value={'status':'valid'}), patch.object(db,'_set_exam_state',side_effect=fail):
            with self.assertRaises(RuntimeError):
                db.start_exam_validated()
        self.assertEqual(db.get_exam_state(),'waiting')

    def test_stop_during_package_lock_prevents_stale_selection(self):
        db.reset_student_category('ACCESS01')
        original=db.lock_student_category
        def stop_then_lock(*args,**kwargs):
            db.set_exam_state('finished')
            return original(*args,**kwargs)
        with patch.object(db,'lock_student_category',side_effect=stop_then_lock):
            r=self.client.post('/api/student/select-category',json={**self.payload,'category':'A'})
        self.assertEqual(r.status_code,403)
        with closing(db.get_sqlite_conn()) as conn:
            self.assertFalse(conn.execute("SELECT selected_category FROM users WHERE nim='ACCESS01'").fetchone()[0])

    def test_lost_submit_response_history_recovers_and_retry_keeps_best(self):
        with patch.object(db,'evaluate_sql_submission',return_value=self.grade):
            self.client.post('/api/student/submit',json=self.payload)  # response discarded
            stored=db.get_student_submissions(self.user['id'])[self.qid]
            self.assertEqual(stored['latest_attempt']['submitted_query'],'SELECT 1')
            self.assertEqual(stored['score'],10)
            self.assertEqual(self.client.post('/api/student/submit',json=self.payload).status_code,200)
        self.assertEqual(self.submission_count(),1)
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM submission_attempts').fetchone()[0],2)

    def test_cleared_previous_session_cannot_enter_new_exam(self):
        self.assertEqual(self.client.post('/api/admin/clear-sessions',json={'clear_logs':False}).status_code,200)
        with patch('grading_engine.validate_reference',return_value={'status':'valid'}):
            self.assertEqual(self.client.post('/api/admin/exam/start').status_code,200)
        for url in ('/api/student/questions','/api/exam/state'):
            self.assertEqual(self.client.get(url).status_code,401)
        with patch.object(db,'evaluate_sql_submission') as grade:
            self.assertEqual(self.client.post('/api/student/submit',json=self.payload).status_code,401)
            grade.assert_not_called()


if __name__=='__main__':
    unittest.main(verbosity=2)
