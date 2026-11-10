"""Real PostgreSQL parity and sandbox isolation for the shared admin/student IDE."""
from contextlib import closing
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment
ensure_test_environment()
from fastapi.testclient import TestClient
from admin_test_support import authenticate_admin
import admin_practice
import database as db
import main
import sandbox_roles


class PracticePostgresTests(unittest.TestCase):
    def setUp(self):
        db.set_exam_state('waiting')
        db.create_package('IDE-PARITY','IDE Parity','Real PostgreSQL integration',1)
        questions=db.get_questions_by_category('IDE-PARITY')
        self.qid=questions[0]['id'] if questions else db.save_question(1,'SELECT fixture','Return 1 as v',10,'SELECT 1 AS v',category='IDE-PARITY')
        self.admin=TestClient(main.app)
        self.addCleanup(self.admin.close)
        authenticate_admin(self.admin)
        html=self.admin.get('/admin/practice').text
        self.payload={'nim':re.search(r'data-nim="([^"]+)"',html)[1], 'session_token':re.search(r'data-token="([^"]+)"',html)[1]}
        self.assertEqual(self.admin.post('/api/admin/practice/select-category',json={**self.payload,'category':'IDE-PARITY'}).status_code,200)
        self.actor=admin_security_session(self.admin)
        self.addCleanup(db.cleanup_student_sandbox_schema,self.payload['nim'])

    def test_real_select_grading_matches_student(self):
        db.set_exam_state('active')
        student=TestClient(main.app)
        self.addCleanup(student.close)
        self.assertEqual(student.post('/login',data={'nim':'IDE-STUDENT','name':'IDE Student','device_id':'ide-student'},follow_redirects=False).status_code,302)
        payload={'nim':student.cookies['student_nim'],'session_token':student.cookies['student_token']}
        self.assertEqual(student.post('/api/student/select-category',json={**payload,'category':'IDE-PARITY'}).status_code,200)
        for query in ('SELECT 1 AS v','SELECT 2 AS v','SELECT 1.0::numeric AS v'):
            admin_result=self.admin.post('/api/admin/practice/submit',json={**self.payload,'query':query,'question_id':self.qid,'active_database':'pagila'})
            student_result=student.post('/api/student/submit',json={**payload,'query':query,'question_id':self.qid,'active_database':'pagila'})
            self.assertEqual(admin_result.status_code,200,admin_result.text)
            self.assertEqual(student_result.status_code,200,student_result.text)
            a,b=admin_result.json(),student_result.json()
            for key in ('graded','score','score_retained','eval_status','feedback','columns','rows','error'):
                self.assertEqual(a[key],b[key],key)
            self.assertEqual(a['latest_attempt']['is_correct'],b['latest_attempt']['is_correct'])

    def test_real_sandbox_is_separate_from_student(self):
        create=self.admin.post('/api/admin/practice/run-query',json={**self.payload,'query':'CREATE TABLE admin_only(id INT); INSERT INTO admin_only VALUES(7);','active_database':'sandbox_pribadi'})
        self.assertEqual(create.status_code,200)
        self.assertTrue(create.json()['success'],create.text)
        select=self.admin.post('/api/admin/practice/run-query',json={**self.payload,'query':'SELECT id FROM admin_only','active_database':'sandbox_pribadi'})
        self.assertEqual(select.json()['rows'],[[7]])
        outsider='IDE-OUTSIDER'
        self.addCleanup(db.cleanup_student_sandbox_schema,outsider)
        missing=db.execute_student_query('SELECT id FROM admin_only',active_db='sandbox_pribadi',nim=outsider)
        self.assertFalse(missing['success'])
        schema,_=sandbox_roles.identity(self.payload['nim'])
        blocked=db.execute_student_query(f'SELECT id FROM {schema}.admin_only',active_db='sandbox_pribadi',nim=outsider)
        self.assertFalse(blocked['success'])
        self.assertNotEqual(sandbox_roles.identity(outsider),sandbox_roles.identity(self.payload['nim']))

    def test_real_payment_report_with_extract_runs(self):
        query="""SELECT DATE_part('month',p.payment_date) AS bulan,
            UPPER(c.name) AS kategori, COUNT(p.payment_id) AS jumlah_pembayaran,
            SUM(p.amount) AS total_pendapatan, round(AVG(p.amount),2) AS rata_rata_pembayaran
            FROM payment p JOIN rental r ON r.rental_id=p.rental_id
            JOIN inventory i ON i.inventory_id=r.inventory_id
            JOIN film f ON f.film_id=i.film_id
            JOIN film_category fc ON fc.film_id=f.film_id
            JOIN category c ON c.category_id=fc.category_id
            WHERE EXTRACT(YEAR FROM p.payment_date)=2025
            GROUP BY DATE_part('month',p.payment_date),c.name
            ORDER BY bulan,total_pendapatan DESC"""
        r=self.admin.post('/api/admin/practice/run-query',json={**self.payload,'query':query,'active_database':'pagila'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['success'],r.text)
        self.assertEqual(r.json()['columns'],['bulan','kategori','jumlah_pembayaran','total_pendapatan','rata_rata_pembayaran'])

    def test_practice_worker_grades_pending_in_separate_store(self):
        pending={'graded':False,'is_correct':None,'score':None,'eval_status':'evaluation_limit','feedback':'Pending fixture','student_result':{}}
        with patch.object(db,'evaluate_sql_submission',return_value=pending):
            r=self.admin.post('/api/admin/practice/submit',json={**self.payload,'query':'SELECT 1 AS v','question_id':self.qid,'active_database':'pagila'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['queue_status'],'queued')
        self.assertTrue(admin_practice.Worker().run_once())
        scores=self.admin.get('/api/admin/practice/questions').json()['submissions']
        self.assertEqual(scores[str(self.qid)]['score'],10)
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM users WHERE nim=?',(self.payload['nim'],)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM submissions WHERE question_id=?',(self.qid,)).fetchone()[0],0)


def admin_security_session(client):
    import admin_security
    return admin_security.get_session(client.cookies['admin_session'])


if __name__=='__main__':
    unittest.main(verbosity=2)
