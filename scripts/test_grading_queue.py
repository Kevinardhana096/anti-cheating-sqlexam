"""Durability, leases, grading history, revision fencing, and concurrent admin decisions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database as db
import grading_queue as queue
import main
from admin_test_support import authenticate_admin
from fastapi.testclient import TestClient


class QueueTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='sqlexam_queue_')
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ,{'EXAM_SQLITE_PATH':str(Path(directory.name)/'exam.db'),'ADMIN_MASTER_KEY':'queue-test-master'})
        env.start()
        self.addCleanup(env.stop)
        postgres = patch.object(db.psycopg2,'connect',side_effect=AssertionError('Unit tests must not connect to PostgreSQL'))
        postgres.start()
        self.addCleanup(postgres.stop)
        db.init_system_db()
        self.qid = db.save_question(987,'Queue fixture','Queue fixture',10,'SELECT 1 AS v',category='A',target_database='pagila')
        ok,self.user,_ = db.login_student('QUEUE01','Queue Student','testclient','queue-token')
        self.assertTrue(ok)
        db.lock_student_category('QUEUE01','A')
        db.set_exam_state('active')
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        authenticate_admin(self.client)
        self.worker = queue.Worker()
        self.correct = {'graded':True,'score':10,'is_correct':True,'eval_status':'correct','feedback':'Correct'}

    def question(self):
        return db.get_question_by_id(self.qid)

    def pending(self, status='evaluation_limit', query='SELECT 1 AS v'):
        return db.save_submission(self.user['id'],self.qid,query,None,None,status,'Pending',graded=False)

    def rows(self, table):
        with closing(db.get_sqlite_conn()) as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY id')]

    def run_correct(self):
        with patch.object(db,'evaluate_sql_submission',return_value=self.correct):
            return self.worker.run_once()

    def test_pending_is_queued_in_same_transaction_and_worker_preserves_original(self):
        saved = self.pending()
        self.assertEqual(saved['queue_status'],'queued')
        self.assertTrue(self.run_correct())
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'completed')
        self.assertEqual(len(self.rows('submission_attempts')),1)
        self.assertIsNone(self.rows('submission_attempts')[0]['score'])
        best = db.get_student_submissions(self.user['id'])[self.qid]
        self.assertEqual(best['score'],10)
        self.assertEqual(best['latest_attempt']['score'],10)
        self.assertIsNone(best['latest_attempt']['initial_result']['score'])
        self.assertFalse(self.worker.run_once())

    def test_two_workers_cannot_claim_same_job(self):
        self.pending()
        with ThreadPoolExecutor(2) as executor:
            claims = list(executor.map(lambda _:queue.claim(),range(2)))
        self.assertEqual(sum(item is not None for item in claims),1)
        self.assertEqual(self.rows('grading_jobs')[0]['tries'],1)

    def test_expired_lease_old_worker_cannot_commit(self):
        self.pending()
        first = queue.claim()
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('UPDATE grading_jobs SET lease_until=0')
        second = queue.claim()
        self.assertNotEqual(first['job']['lease_token'],second['job']['lease_token'])
        self.assertFalse(queue.finish(first,self.correct))
        self.assertTrue(queue.finish(second,self.correct))
        self.assertFalse(queue.finish(second,self.correct))
        self.assertEqual(len(self.rows('grading_decisions')),1)

    def test_claim_survives_process_exit_and_new_worker_recovers(self):
        self.pending()
        result = subprocess.run([sys.executable,'-c',"import grading_queue; assert grading_queue.claim()['job']['id']"],
                                cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'running')
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('UPDATE grading_jobs SET lease_until=0')
        self.worker = queue.Worker()
        self.assertTrue(self.run_correct())
        self.assertEqual(self.rows('grading_jobs')[0]['tries'],2)

    def test_accepted_answer_can_finish_after_normal_stop(self):
        self.pending()
        db.set_exam_state('finished')
        self.assertTrue(self.run_correct())
        self.assertEqual(self.rows('submissions')[0]['score'],10)

    def test_new_exam_cycle_fences_old_job(self):
        self.pending()
        db.set_exam_state('finished')
        db.set_exam_state('active')
        self.assertTrue(self.run_correct())
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'stale')
        self.assertEqual(self.rows('submissions'),[])

    def test_question_changed_during_evaluation_cannot_write_score(self):
        self.pending()
        claim = queue.claim()
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('UPDATE questions SET question_revision=question_revision+1 WHERE id=?',(self.qid,))
        self.assertFalse(queue.finish(claim,self.correct))
        self.assertEqual(self.rows('submissions'),[])

    def test_reset_then_reselect_same_package_does_not_revive_old_job(self):
        self.pending()
        db.reset_student_category('QUEUE01')
        db.lock_student_category('QUEUE01','A')
        self.run_correct()
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'stale')
        self.assertEqual(self.rows('submissions'),[])

    def test_delete_user_cascades_job_and_running_worker_cannot_resurrect(self):
        self.pending()
        claim = queue.claim()
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('DELETE FROM users WHERE id=?',(self.user['id'],))
        self.assertFalse(queue.finish(claim,self.correct))
        self.assertEqual(self.rows('grading_jobs'),[])
        self.assertEqual(self.rows('submissions'),[])

    def test_reference_and_manual_and_unsnapshotted_sandbox_are_review_only(self):
        for status in ('reference_error','manual_review'):
            self.assertEqual(self.pending(status)['queue_status'],'review')
        db.set_exam_state('finished')
        q = self.question()
        db.save_question(q['question_number'],q['title'],q['description'],10,'CREATE TABLE x(id INT)',self.qid,category='A',target_database='sandbox_pribadi')
        self.assertEqual(self.pending()['queue_status'],'review')
        self.assertFalse(self.worker.run_once())

    def test_sandbox_with_explicit_setup_can_be_replayed(self):
        db.set_exam_state('finished')
        q = self.question()
        db.save_question(q['question_number'],q['title'],q['description'],10,'SELECT id FROM x',self.qid,category='A',target_database='sandbox_pribadi',setup_query='CREATE TABLE x(id INT); INSERT INTO x VALUES(1)')
        self.assertEqual(self.pending(query='SELECT id FROM x')['queue_status'],'queued')
        self.assertTrue(self.run_correct())

    def test_repeated_evaluator_failure_becomes_review_and_never_zero(self):
        self.pending()
        error = {'graded':False,'score':None,'is_correct':None,'eval_status':'evaluation_error','feedback':'Temporary failure'}
        with patch.object(db,'evaluate_sql_submission',return_value=error):
            for _ in range(queue.MAX_ATTEMPTS):
                self.assertTrue(self.worker.run_once())
                with closing(db.get_sqlite_conn()) as conn,conn:
                    conn.execute('UPDATE grading_jobs SET run_after=0')
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'review')
        self.assertEqual(self.rows('submissions'),[])
        self.assertTrue(all(row['score'] is None for row in self.rows('grading_decisions')))

    def test_failure_of_regrade_keeps_prior_best(self):
        first = db.save_submission(self.user['id'],self.qid,'SELECT 1 AS v',1,10,'correct','Correct')
        queue.regrade(first['attempt_id'],self.question()['question_revision'],0,'admin-a')
        with patch.object(db,'evaluate_sql_submission',return_value={'graded':False,'is_correct':None,'score':None,'eval_status':'reference_error','feedback':'Reference failed'}):
            self.worker.run_once()
        self.assertEqual(self.rows('submissions')[0]['score'],10)
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'review')

    def test_manual_partial_grade_and_optimistic_conflict(self):
        saved = self.pending('manual_review')
        first = queue.manual(saved['attempt_id'],self.question()['question_revision'],0,6,'Partial credit','admin-a')
        self.assertEqual(self.rows('submissions')[0]['score'],6)
        with self.assertRaises(db.StudentAccessError):
            queue.manual(saved['attempt_id'],self.question()['question_revision'],0,9,'Stale second admin','admin-b')
        self.assertEqual(len(self.rows('grading_decisions')),1)
        self.assertEqual(self.rows('grading_decisions')[0]['admin_session_id'],'admin-a')

    def test_manual_correction_rebuilds_best_instead_of_retaining_wrong_high_score(self):
        old = db.save_submission(self.user['id'],self.qid,'SELECT 1 AS v',1,10,'correct','Correct')
        db.save_submission(self.user['id'],self.qid,'SELECT 2 AS v',0,7,'partial','Partial')
        queue.manual(old['attempt_id'],self.question()['question_revision'],0,0,'Prior grade corrected','admin-a')
        self.assertEqual(self.rows('submissions')[0]['score'],7)
        self.assertEqual(self.rows('submissions')[0]['submitted_query'],'SELECT 2 AS v')

    def test_manual_grade_fences_running_auto_job(self):
        saved = self.pending()
        claim = queue.claim()
        queue.manual(saved['attempt_id'],self.question()['question_revision'],0,3,'Manual decision wins','admin-a')
        self.assertFalse(queue.finish(claim,self.correct))
        self.assertEqual(self.rows('submissions')[0]['score'],3)

    def test_manual_score_outside_weight_rejected(self):
        saved = self.pending('manual_review')
        with self.assertRaises(db.StudentAccessError):
            queue.manual(saved['attempt_id'],self.question()['question_revision'],0,11,'Invalid','admin-a')
        self.assertEqual(self.rows('grading_decisions'),[])

    def test_explicit_regrade_of_old_revision_uses_current_revision(self):
        old = db.save_submission(self.user['id'],self.qid,'SELECT 1 AS v',1,10,'correct','Correct')
        db.set_exam_state('finished')
        q = self.question()
        db.save_question(q['question_number'],q['title'],q['description'],10,'SELECT 2 AS v',self.qid,category='A',target_database='pagila')
        current = self.question()['question_revision']
        queue.regrade(old['attempt_id'],current,0,'admin-a')
        wrong = {**self.correct,'score':0,'is_correct':False,'eval_status':'wrong_data'}
        with patch.object(db,'evaluate_sql_submission',return_value=wrong):
            self.worker.run_once()
        self.assertEqual(self.rows('submissions')[0]['score'],0)
        self.assertEqual(self.rows('submissions')[0]['question_revision'],current)

    def test_duplicate_regrade_is_not_enqueued_twice(self):
        saved = self.pending('reference_error')
        queue.regrade(saved['attempt_id'],self.question()['question_revision'],0,'admin-a')
        with self.assertRaises(db.StudentAccessError):
            queue.regrade(saved['attempt_id'],self.question()['question_revision'],0,'admin-b')
        self.assertEqual(len(self.rows('grading_jobs')),1)

    def test_dataset_maintenance_fences_jobs_and_blocks_new_exam(self):
        self.pending()
        claim = queue.claim()
        db.set_exam_state('finished')
        with queue.dataset_maintenance():
            self.assertIsNone(queue.claim())
            with self.assertRaises(ValueError):
                db.start_exam_validated()
            with self.assertRaises(db.StudentAccessError):
                queue.regrade(claim['attempt']['id'],self.question()['question_revision'],0,'admin-a')
        self.assertFalse(queue.finish(claim,self.correct))
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'stale')

    def test_dataset_reset_disallowed_while_exam_active(self):
        with self.assertRaises(db.StudentAccessError),queue.dataset_maintenance():
            self.fail('Should not enter maintenance')

    def test_admin_endpoints_require_auth_csrf_and_guard_conflicts(self):
        saved = self.pending('manual_review')
        endpoint = f"/api/admin/grading/attempts/{saved['attempt_id']}/manual"
        body = {'score':5,'reason':'Manual partial','question_revision':self.question()['question_revision'],'expected_decision_id':0}
        self.client.headers.pop('X-CSRF-Token')
        self.assertEqual(self.client.post(endpoint,json=body).status_code,403)
        authenticate_admin(self.client)
        self.assertEqual(self.client.post(endpoint,json=body).status_code,200)
        self.assertEqual(self.client.post(endpoint,json=body).status_code,409)
        detail = self.client.get(f"/api/admin/grading/attempts/{saved['attempt_id']}").json()
        self.assertEqual(detail['attempt']['score'],5)
        self.assertEqual(len(detail['decisions']),1)
        self.assertNotIn('run_token',detail['decisions'][0])
        self.client.cookies.delete('admin_session')
        self.assertEqual(self.client.get('/api/admin/grading/jobs').status_code,403)

    def test_time_dependent_sql_is_not_silently_replayed_later(self):
        self.assertFalse(queue.replayable({**self.question(),'target_database':'sandbox_pribadi (virtual)','setup_query':''}))
        self.assertEqual(self.pending(query='SELECT CURRENT_DATE AS v')['queue_status'],'review')
        self.assertEqual(self.pending(query='SELECT now()::date AS v')['queue_status'],'review')
        for query in ('SELECT random() AS v','SELECT clock_timestamp() AS v','SELECT gen_random_uuid() AS v'):
            with self.subTest(query=query):
                self.assertEqual(self.pending(query=query)['queue_status'],'review')

    def test_two_admins_racing_manual_decision_have_one_winner(self):
        saved = self.pending('manual_review')
        revision = self.question()['question_revision']
        def decide(actor):
            try:
                queue.manual(saved['attempt_id'],revision,0,5,'Concurrent decision',actor)
                return 200
            except db.StudentAccessError as error:
                return error.status_code
        with ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(decide,['admin-a','admin-b'])),[200,409])
        self.assertEqual(len(self.rows('grading_decisions')),1)

    def test_migration_backfills_old_pending_as_review_once(self):
        self.pending()
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('DROP TABLE grading_decisions')
            conn.execute('DROP TABLE grading_jobs')
            conn.execute('PRAGMA user_version=4')
        db.init_system_db()
        db.init_system_db()
        self.assertEqual(len(self.rows('grading_jobs')),1)
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'review')
        self.assertFalse(self.worker.run_once())

    def test_queue_migration_failure_rolls_back(self):
        saved = self.pending()
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute('DROP TABLE grading_decisions')
            conn.execute('DROP TABLE grading_jobs')
            conn.execute('PRAGMA user_version=4')
        def broken(conn):
            conn.execute('CREATE TABLE grading_jobs(id INTEGER)')
            raise RuntimeError('migration failed')
        with patch.object(queue,'migrate',side_effect=broken),self.assertRaises(RuntimeError):
            db.init_system_db()
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='grading_jobs'").fetchone())
            self.assertEqual(conn.execute('SELECT id FROM submission_attempts').fetchone()[0],saved['attempt_id'])

    def test_restore_preserves_decisions_and_never_resumes_old_queued_work(self):
        from exam_backup import create_backup,restore_backup
        root = Path(os.environ['EXAM_SQLITE_PATH']).parent
        saved = self.pending()
        create_backup(os.environ['EXAM_SQLITE_PATH'],root/'bundle')
        restore_backup(root/'bundle',root/'restored')
        import sqlite3
        with closing(sqlite3.connect(root/'restored/exam_system.db')) as conn:
            self.assertEqual(conn.execute('SELECT status FROM grading_jobs').fetchone()[0],'stale')
            self.assertIsNone(conn.execute('SELECT session_token FROM users').fetchone()[0])
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'queued')

    def test_score_zero_can_be_a_completed_manual_grade(self):
        saved = self.pending('manual_review')
        decision = queue.manual(saved['attempt_id'],self.question()['question_revision'],0,0,'No credit','admin-a')
        self.assertGreater(decision,0)
        self.assertEqual(self.rows('submissions')[0]['score'],0)
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'cancelled')

    def test_dataset_reset_wrapper_enforces_fence_even_for_direct_calls(self):
        self.pending()
        with patch.object(db,'_reset_target_database_impl',return_value=(True,'Reset')) as reset:
            with self.assertRaises(db.StudentAccessError):
                db.reset_target_database('pagila')
            reset.assert_not_called()
            db.set_exam_state('finished')
            self.assertTrue(db.reset_target_database('pagila')[0])
        self.assertEqual(self.rows('grading_jobs')[0]['status'],'stale')
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(queue.setting(conn,'grading_maintenance',''),'')
            self.assertEqual(queue.setting(conn,'dataset_revision'),'1')

    def test_offline_maintenance_recovery_requires_matching_revision(self):
        import recover_grading_maintenance as recovery
        db.set_exam_state('finished')
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute("INSERT INTO system_settings(key,value) VALUES('grading_maintenance','abandoned')")
            conn.execute("INSERT INTO system_settings(key,value) VALUES('dataset_revision','7')")
        with patch.object(sys,'argv',['recover','--server-stopped','--expected-dataset-revision','6']),self.assertRaises(SystemExit):
            recovery.main()
        with patch.object(sys,'argv',['recover','--server-stopped','--expected-dataset-revision','7']):
            recovery.main()
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(queue.setting(conn,'grading_maintenance',''),'')
            self.assertEqual(queue.setting(conn,'dataset_revision'),'8')


if __name__=='__main__':
    unittest.main(verbosity=2)
