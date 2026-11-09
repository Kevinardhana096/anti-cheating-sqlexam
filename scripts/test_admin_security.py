"""Independent admin sessions, CSRF, credential lifecycle, and authenticated telemetry."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database as db
import admin_security as auth
import main
from fastapi.testclient import TestClient


class AdminSecurityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='sqlexam_admin_')
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {'EXAM_SQLITE_PATH':str(Path(directory.name)/'exam.db'),
                                               'ADMIN_MASTER_KEY':'shared-test-key-123'})
        environment.start()
        self.addCleanup(environment.stop)
        postgres = patch.object(db.psycopg2, 'connect', side_effect=AssertionError('No production PostgreSQL in unit tests'))
        postgres.start()
        self.addCleanup(postgres.stop)
        limiter = patch.object(main, 'rate_limiter', main.InMemoryRateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)
        db.init_system_db()
        self.a = self.client()
        self.b = self.client()

    def client(self):
        client = TestClient(main.app)
        self.addCleanup(client.close)
        return client

    def login(self, client, key='shared-test-key-123', csrf_header=True):
        self.assertEqual(client.get('/admin/login').status_code, 200)
        response = client.post('/admin/login', data={'master_key':key, 'csrf_token':client.cookies.get('admin_login_csrf')}, follow_redirects=False)
        if response.status_code == 303 and response.headers['location'] == '/admin' and csrf_header:
            token = client.cookies.get('admin_session')
            client.headers['X-CSRF-Token'] = auth.csrf_token(token)
        return response

    def test_two_admins_control_independently(self):
        self.assertEqual(self.login(self.a).headers['location'], '/admin')
        self.assertEqual(self.login(self.b).headers['location'], '/admin')
        self.assertNotEqual(self.a.cookies.get('admin_session'), self.b.cookies.get('admin_session'))
        for client in (self.a, self.b):
            self.assertEqual(client.get('/api/admin/students').status_code, 200)
            self.assertEqual(client.post('/api/admin/exam/stop').status_code, 200)
        self.assertEqual(self.a.post('/admin/logout', follow_redirects=False).status_code, 303)
        self.assertEqual(self.a.get('/api/admin/students').status_code, 403)
        self.assertEqual(self.b.get('/api/admin/students').status_code, 200)

    def test_simultaneous_logins_do_not_revoke_either(self):
        with ThreadPoolExecutor(2) as executor:
            results = list(executor.map(lambda c:self.login(c), (self.a,self.b)))
        self.assertTrue(all(r.status_code == 303 for r in results))
        self.assertTrue(all(c.get('/api/admin/students').status_code == 200 for c in (self.a,self.b)))

    def test_relogin_rotates_only_current_session(self):
        self.login(self.a)
        self.login(self.b)
        old = self.a.cookies.get('admin_session')
        self.login(self.a)
        self.assertIsNone(auth.get_session(old))
        self.assertEqual(self.b.get('/api/admin/students').status_code, 200)

    def test_raw_tokens_and_password_are_not_stored(self):
        self.login(self.a)
        raw = self.a.cookies.get('admin_session')
        with closing(db.get_sqlite_conn()) as conn:
            session = dict(conn.execute('SELECT * FROM admin_sessions').fetchone())
            logs = [tuple(row) for row in conn.execute('SELECT * FROM admin_audit')]
        self.assertNotIn(raw, str(session)+str(logs))
        self.assertNotIn('shared-test-key-123', db.get_admin_master_key()+str(logs))
        self.assertTrue(auth.check_key('shared-test-key-123', db.get_admin_master_key()))

    def test_session_survives_new_process(self):
        self.login(self.a)
        raw = self.a.cookies.get('admin_session')
        result = subprocess.run([sys.executable,'-c','import sys,admin_security; assert admin_security.get_session(sys.stdin.read())'],
                                input=raw, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_expired_and_idle_sessions_are_rejected(self):
        self.login(self.a)
        self.login(self.b)
        with closing(db.get_sqlite_conn()) as conn, conn:
            conn.execute('UPDATE admin_sessions SET expires_at=? WHERE token_hash=?', (int(time.time())-1,auth.fingerprint(self.a.cookies.get('admin_session'))))
            conn.execute('UPDATE admin_sessions SET last_seen=? WHERE token_hash=?', (int(time.time())-auth.IDLE_SECONDS-1,auth.fingerprint(self.b.cookies.get('admin_session'))))
        self.assertEqual(self.a.get('/api/admin/students').status_code, 403)
        self.assertEqual(self.b.get('/api/admin/students').status_code, 403)

    def test_missing_wrong_and_cross_session_csrf_are_rejected(self):
        self.login(self.a, csrf_header=False)
        self.login(self.b)
        for value in (None, 'wrong', self.b.headers['X-CSRF-Token']):
            if value is None:
                self.a.headers.pop('X-CSRF-Token', None)
            else:
                self.a.headers['X-CSRF-Token'] = value
            self.assertEqual(self.a.post('/api/admin/exam/stop').status_code, 403)
        self.assertNotEqual(db.get_exam_state(), 'finished')

    def test_bad_origins_and_referers_cannot_bypass_check(self):
        self.login(self.a)
        for headers in ({'Origin':'http://evil.test'}, {'Referer':'http://evil.test/path'},
                        {'Origin':'null'}, {'Referer':'malformed'}, {'Sec-Fetch-Site':'cross-site'},
                        {'Origin':'http://testserver', 'Referer':'http://evil.test/path'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.a.post('/api/admin/exam/stop', headers=headers).status_code, 403)
        self.assertEqual(self.a.post('/api/admin/exam/stop', headers={'Origin':'http://testserver'}).status_code, 200)

    def test_login_requires_bound_form_token(self):
        self.assertEqual(self.a.post('/admin/login',data={'master_key':'shared-test-key-123'}).status_code, 403)
        self.a.get('/admin/login')
        self.b.get('/admin/login')
        self.assertEqual(self.a.post('/admin/login',data={'master_key':'shared-test-key-123','csrf_token':self.b.cookies.get('admin_login_csrf')}).status_code, 403)

    def test_login_is_rate_limited(self):
        for _ in range(6):
            self.assertEqual(self.login(self.a,key='incorrect').status_code, 303)
        self.assertEqual(self.login(self.a).status_code, 429)

    def test_get_logout_does_not_change_session(self):
        self.login(self.a)
        self.assertEqual(self.a.get('/admin/logout').status_code, 405)
        self.assertEqual(self.a.get('/api/admin/students').status_code, 200)

    def test_password_change_revokes_other_admin_and_keeps_initiator(self):
        self.login(self.a)
        self.login(self.b)
        old = self.a.cookies.get('admin_session')
        response = self.a.post('/api/admin/change-password', json={'current_password':'shared-test-key-123','new_password':'replacement-master-key'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(auth.get_session(old))
        self.assertEqual(self.a.get('/api/admin/students').status_code, 200)
        self.assertEqual(self.b.get('/api/admin/students').status_code, 403)
        db.init_system_db()
        self.assertTrue(auth.check_key('replacement-master-key', db.get_admin_master_key()))
        self.assertFalse(auth.check_key('shared-test-key-123', db.get_admin_master_key()))

    def test_invalid_password_change_has_no_effect(self):
        self.login(self.a)
        for old, new in [('wrong','replacement-key-long'), ('shared-test-key-123','short')]:
            self.assertEqual(self.a.post('/api/admin/change-password',json={'current_password':old,'new_password':new}).status_code, 400)
        self.assertTrue(auth.check_key('shared-test-key-123', db.get_admin_master_key()))
        self.assertEqual(self.a.get('/api/admin/students').status_code, 200)

    def test_audit_distinguishes_admin_sessions_and_excludes_secrets(self):
        self.login(self.a)
        self.login(self.b)
        for client in (self.a,self.b):
            client.post('/api/admin/exam/stop')
        response = self.a.get('/api/admin/audit')
        self.assertEqual(response.status_code, 200)
        events = [r for r in response.json()['records'] if r['path']=='/api/admin/exam/stop']
        self.assertEqual(len({r['session_id'] for r in events}), 2)
        self.assertEqual(self.client().get('/api/admin/audit').status_code, 403)
        self.assertNotIn(self.a.cookies.get('admin_session'), response.text)

    def test_admin_pages_are_not_cached(self):
        self.login(self.a)
        for path in ('/admin','/admin/login','/api/admin/students','/api/admin/session'):
            self.assertIn('no-store', self.a.get(path).headers['cache-control'])

    def student(self):
        db.set_exam_state('active')
        ok,user,_ = db.login_student('SECLOG','Student','testclient','student-token')
        self.assertTrue(ok)
        db.lock_student_category('SECLOG','A')
        return user, {'nim':'SECLOG','session_token':'student-token','action_type':'blur_tab','details':'Client event'}

    def test_invalid_student_log_cannot_append(self):
        _, payload = self.student()
        with closing(db.get_sqlite_conn()) as conn:
            before = conn.execute('SELECT COUNT(*) FROM exam_logs').fetchone()[0]
        response = self.a.post('/api/student/log-event',json={**payload,'session_token':'forged'})
        self.assertEqual(response.status_code, 401)
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM exam_logs').fetchone()[0], before)

    def test_student_cannot_forge_admin_events_or_oversized_details(self):
        _, payload = self.student()
        self.assertEqual(self.a.post('/api/student/log-event',json={**payload,'action_type':'exam_started'}).status_code, 422)
        self.assertEqual(self.a.post('/api/student/log-event',json={**payload,'details':'x'*1001}).status_code, 422)
        self.assertEqual(self.a.post('/api/student/log-event',json=payload).status_code, 200)
        with closing(db.get_sqlite_conn()) as conn:
            row = conn.execute("SELECT details FROM exam_logs WHERE action_type='blur_tab'").fetchone()
        self.assertTrue(row[0].startswith('Laporan klien:'))

    def test_student_logging_requires_active_valid_session_and_rate_limit(self):
        _, payload = self.student()
        for _ in range(60):
            self.assertEqual(self.a.post('/api/student/log-event',json=payload).status_code, 200)
        self.assertEqual(self.a.post('/api/student/log-event',json=payload).status_code, 429)
        db.set_exam_state('finished')
        self.assertEqual(self.a.post('/api/student/log-event',json=payload).status_code, 403)

    def test_plaintext_legacy_key_is_hashed_without_changing_value(self):
        with closing(db.get_sqlite_conn()) as conn, conn:
            conn.execute("UPDATE system_settings SET value='legacy-password' WHERE key='admin_master_key'")
        db.init_system_db()
        self.assertTrue(auth.check_key('legacy-password',db.get_admin_master_key()))
        self.assertNotEqual(db.get_admin_master_key(), 'legacy-password')

    def test_stale_admin_edit_and_delete_are_rejected(self):
        self.login(self.a)
        self.login(self.b)
        q = db.get_all_questions(include_expected_query=True)[0]
        body = {'question_id':q['id'], 'expected_edit_revision':q['edit_revision'],
                'question_number':q['question_number'], 'category':q['category'], 'title':'First admin edit',
                'description':'Question text', 'score_weight':10, 'expected_query':'SELECT 1', 'target_database':'pagila'}
        first = self.a.post('/api/admin/questions',json=body)
        self.assertEqual(first.status_code, 200, first.text)
        conflict = self.b.post('/api/admin/questions',json={**body,'title':'Stale second edit'})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(db.get_question_by_id(q['id'])['title'], 'First admin edit')
        self.assertEqual(self.b.delete(f"/api/admin/questions/{q['id']}?expected_edit_revision={q['edit_revision']}").status_code,409)
        current = db.get_question_by_id(q['id'])['edit_revision']
        self.assertEqual(self.b.delete(f"/api/admin/questions/{q['id']}?expected_edit_revision={current}").status_code,200)

    def test_csv_neutralizes_formulas_and_zip_paths_are_flat(self):
        import csv
        import io
        import zipfile
        output = io.StringIO()
        db.safe_csv_writer(output).writerow(['=1+1',' \t@SUM(1)',-3,'normal'])
        self.assertEqual(next(csv.reader(io.StringIO(output.getvalue()))), ["'=1+1","' \t@SUM(1)",'-3','normal'])
        ok,user,_ = db.login_student('ZIPPATH','Export Student','testclient','zip-token')
        self.assertTrue(ok)
        # Legacy/imported metadata can predate the login validator.
        with closing(db.get_sqlite_conn()) as conn, conn:
            conn.execute('UPDATE users SET nim=? WHERE id=?',('../ZIP/path',user['id']))
        with zipfile.ZipFile(io.BytesIO(db.export_submissions_zip_bytes())) as archive:
            self.assertTrue(all('/' not in name and '\\' not in name and '..' not in name for name in archive.namelist()))

    def test_telemetry_rechecks_cutoff_in_final_transaction(self):
        user,payload = self.student()
        context = db.require_student_access(payload['nim'],payload['session_token'],'testclient',active=True,category=True)
        db.set_exam_state('finished')
        with self.assertRaises(db.StudentAccessError):
            db.log_student_event(context,'blur_tab','late event')
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM exam_logs WHERE action_type='blur_tab'").fetchone()[0],0)

    def test_student_logout_requires_post_and_bound_token(self):
        _,payload = self.student()
        self.a.cookies.set('student_nim',payload['nim'])
        self.a.cookies.set('student_token',payload['session_token'])
        self.assertEqual(self.a.get('/logout').status_code,405)
        self.assertEqual(self.a.post('/logout').status_code,403)
        self.assertTrue(db.validate_student_session(payload['nim'],payload['session_token'],'testclient')[0])
        self.assertEqual(self.a.post('/logout',data={'session_token':payload['session_token']},follow_redirects=False).status_code,302)
        self.assertFalse(db.validate_student_session(payload['nim'],payload['session_token'],'testclient')[0])

    def test_rate_limiter_bounds_untrusted_key_storage(self):
        limiter = main.InMemoryRateLimiter()
        for n in range(10000):
            self.assertTrue(limiter.check(str(n),1,60))
        self.assertFalse(limiter.check('overflow',1,60))
        self.assertEqual(len(limiter._history),10000)

    def test_local_recovery_rotates_key_and_revokes_sessions(self):
        import io
        from contextlib import redirect_stdout
        import reset_admin_key
        self.login(self.a)
        with patch.object(reset_admin_key.getpass,'getpass',side_effect=['recovered-key-123','recovered-key-123']), redirect_stdout(io.StringIO()):
            reset_admin_key.main()
        self.assertTrue(auth.check_key('recovered-key-123', db.get_admin_master_key()))
        self.assertEqual(self.a.get('/api/admin/students').status_code,403)

    def test_local_recovery_mismatch_does_not_change_key(self):
        import reset_admin_key
        encoded = db.get_admin_master_key()
        with patch.object(reset_admin_key.getpass,'getpass',side_effect=['recovered-key-123','different-key-123']), self.assertRaises(SystemExit):
            reset_admin_key.main()
        self.assertEqual(db.get_admin_master_key(),encoded)


if __name__ == '__main__':
    unittest.main(verbosity=2)
