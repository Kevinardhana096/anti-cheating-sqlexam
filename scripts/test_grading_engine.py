"""Complete result grading and disposable DDL/DML workspaces on an isolated cluster."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment
ensure_test_environment()
import database as db
from grading_engine import validate_reference


class GradingTests(unittest.TestCase):
    def test_order_by_ties_are_not_wrong_answers(self):
        base="SELECT * FROM (VALUES (8,'A',300),(9,'NEW',264),(9,'DRAMA',264),(10,'B',100)) t(bulan,kategori,total)"
        reference=base+' ORDER BY bulan,total DESC'
        result=self.grade(base+' ORDER BY bulan,total DESC,kategori',reference)
        self.assertTrue(result['is_correct'],result)
        result=self.grade(base+' ORDER BY bulan DESC,total DESC',reference)
        self.assertFalse(result['is_correct'],result)
    @classmethod
    def setUpClass(cls):
        cls.nim = 'PHASE4'
        db.login_student(cls.nim, 'Phase Four', 'testclient', 'p4-token')
        cls.schema = db.init_student_sandbox_schema(cls.nim)

    def grade(self, answer, reference, sandbox=False, **kwargs):
        name = 'sandbox_pribadi' if sandbox else 'pagila'
        return db.evaluate_sql_submission(answer, reference, target_db=name, active_db=name, nim=self.nim, **kwargs)

    def test_full_results_and_preview_are_separate(self):
        result = self.grade('SELECT n FROM generate_series(1,1000) n', 'SELECT n FROM generate_series(1,1000) n')
        self.assertTrue(result['is_correct'], result)
        self.assertEqual(result['student_result']['row_count'], 1000)
        self.assertEqual(len(result['student_result']['rows']), 500)
        self.assertTrue(result['student_result']['is_truncated'])
        wrong = self.grade('SELECT n FROM generate_series(1,501) n', 'SELECT n FROM generate_series(1,502) n')
        self.assertEqual(wrong['eval_status'], 'row_count_mismatch', wrong)

    def test_long_text_and_typed_values(self):
        for a, b in [("'001'", "'1'"), ("'a'", "'A'"), ("'"+'x'*4100+"a'", "'"+'x'*4100+"b'"),
                     ('1.000000000000000000000000000001::numeric', '1.000000000000000000000000000002::numeric')]:
            with self.subTest(a=a):
                result = self.grade('SELECT '+a+' AS v', 'SELECT '+b+' AS v')
                self.assertTrue(result['graded'], result)
                self.assertFalse(result['is_correct'], result)

    def test_order_uses_outer_ast_and_policy(self):
        student = 'SELECT n FROM generate_series(1,3) n ORDER BY n DESC'
        reference = 'SELECT n FROM generate_series(1,3) n ORDER BY n'
        self.assertEqual(self.grade(student, reference)['eval_status'], 'wrong_order')
        self.assertTrue(self.grade(student, reference, grading_policy={'row_order':'ignore'})['is_correct'])
        self.assertTrue(self.grade(student, 'SELECT n FROM (SELECT n FROM generate_series(1,3) n ORDER BY n) s')['is_correct'])

    def test_reference_failure_is_pending_student_error_is_zero(self):
        result = self.grade('SELECT 1 AS v', 'SELECT missing FROM no_such_table')
        self.assertFalse(result['graded'], result)
        self.assertIsNone(result['score'])
        self.assertEqual(result['eval_status'], 'reference_error')
        # Runtime reference errors may occur when FETCH reads the actual rows.
        result = self.grade('SELECT 1 AS v', 'SELECT 10/(n-2) AS v FROM generate_series(1,3) n')
        self.assertEqual(result['eval_status'], 'reference_error', result)
        result = self.grade('SELECT missing FROM no_such_table', 'SELECT 1 AS v')
        self.assertTrue(result['graded'], result)
        self.assertEqual(result['score'], 0)

    def test_limit_and_manual_are_pending(self):
        with patch('grading_results.MAX_GRADE_ROWS', 2):
            result = self.grade('SELECT n FROM generate_series(1,3) n', 'SELECT n FROM generate_series(1,3) n')
        self.assertEqual(result['eval_status'], 'evaluation_limit', result)
        self.assertFalse(result['graded'])
        self.assertFalse(self.grade('SELECT 1', '', grading_policy={'mode':'manual'})['graded'])
        self.assertFalse(self.grade('SELECT 1', '')['graded'])

    def test_ddl_signature_constraints_and_isolation(self):
        setup = db.execute_student_query('CREATE TABLE keep_live(id INT PRIMARY KEY); INSERT INTO keep_live VALUES(99)', 'sandbox_pribadi', self.nim)
        self.assertTrue(setup['success'], setup)
        reference = 'CREATE TABLE zparent(a INT,b INT,PRIMARY KEY(a,b)); CREATE TABLE achild(a INT,b INT,FOREIGN KEY(a,b) REFERENCES zparent(a,b));'
        try:
            for _ in range(2):
                result = self.grade(reference, reference, True)
                self.assertTrue(result['is_correct'], result)
            wrong = reference.replace('FOREIGN KEY(a,b) REFERENCES zparent(a,b)', 'FOREIGN KEY(b,a) REFERENCES zparent(a,b)')
            result = self.grade(wrong, reference, True)
            self.assertEqual(result['eval_status'], 'wrong_schema', result)
            live = db.execute_student_query('SELECT * FROM keep_live', 'sandbox_pribadi', self.nim)
            self.assertEqual(live['rows'], [[99]])
            absent = db.execute_student_query('SELECT * FROM zparent', 'sandbox_pribadi', self.nim)
            self.assertFalse(absent['success'])
        finally:
            db.execute_student_query('DROP TABLE keep_live', 'sandbox_pribadi', self.nim)

    def test_dml_snapshot_and_foreign_key_clone_order(self):
        setup = 'CREATE TABLE zparent(a INT PRIMARY KEY); CREATE TABLE achild(a INT REFERENCES zparent(a)); INSERT INTO zparent VALUES(1); INSERT INTO achild VALUES(1)'
        self.assertTrue(db.execute_student_query(setup, 'sandbox_pribadi', self.nim)['success'])
        try:
            result = self.grade('UPDATE achild SET a=1', 'UPDATE achild SET a=1', True)
            self.assertTrue(result['is_correct'], result)
            result = self.grade('UPDATE achild SET a=999', 'UPDATE achild SET a=1', True)
            self.assertEqual(result['eval_status'], 'syntax_error', result)
            self.assertEqual(db.execute_student_query('SELECT * FROM achild', 'sandbox_pribadi', self.nim)['rows'], [[1]])
        finally:
            db.execute_student_query('DROP TABLE achild; DROP TABLE zparent', 'sandbox_pribadi', self.nim)

    def test_explicit_setup_and_validation(self):
        result = self.grade('INSERT INTO fixture VALUES(1)', 'INSERT INTO fixture VALUES(1)', True,
                            setup_query='CREATE TABLE fixture(id INT PRIMARY KEY)')
        self.assertTrue(result['is_correct'], result)
        self.assertEqual(validate_reference('INSERT INTO fixture VALUES(1)', 'sandbox_pribadi',
                         setup_query='CREATE TABLE fixture(id INT PRIMARY KEY)')['status'], 'valid')
        with self.assertRaises(ValueError):
            validate_reference('', 'pagila')

    def test_identity_sequence_and_indexes_survive_snapshot(self):
        setup = 'CREATE TABLE seq_fixture(id INT GENERATED ALWAYS AS IDENTITY (START WITH 10 INCREMENT BY 5), value INT); CREATE UNIQUE INDEX seq_value ON seq_fixture(value); INSERT INTO seq_fixture(value) VALUES(1)'
        self.assertTrue(db.execute_student_query(setup, 'sandbox_pribadi', self.nim)['success'])
        try:
            result = self.grade('INSERT INTO seq_fixture(value) VALUES(2)', 'INSERT INTO seq_fixture(value) VALUES(2)', True)
            self.assertTrue(result['is_correct'], result)
            result = self.grade('SELECT id FROM seq_fixture', 'SELECT id FROM seq_fixture', True)
            self.assertTrue(result['is_correct'], result)
            live = db.execute_student_query('SELECT id,value FROM seq_fixture', 'sandbox_pribadi', self.nim)
            self.assertEqual(live['rows'], [[10, 1]])
        finally:
            db.execute_student_query('DROP TABLE seq_fixture', 'sandbox_pribadi', self.nim)

    def test_update_noop_cannot_be_answered_with_select(self):
        result = self.grade('SELECT 1', 'UPDATE fixture SET id=id', True, setup_query='CREATE TABLE fixture(id INT)')
        self.assertEqual(result['eval_status'], 'missing_dml', result)

    def test_column_reordering_requires_explicit_policy(self):
        reference, answer = "SELECT 1 AS a,'x' AS b", "SELECT 'x' AS b,1 AS a"
        self.assertEqual(self.grade(answer, reference)['eval_status'], 'column_mismatch')
        result = self.grade(answer, reference, grading_policy={'column_order':False})
        self.assertTrue(result['is_correct'], result)
        self.assertEqual(result['student_result']['columns'], ['a', 'b'])
        self.assertEqual(result['student_result']['rows'], [[1, 'x']])

    def test_no_disposable_roles_or_schemas_remain(self):
        from contextlib import closing
        with closing(db.get_pg_admin_connection()) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'sandbox_%'")
            self.assertEqual({r[0] for r in cursor.fetchall()}, {self.schema})


if __name__ == '__main__':
    unittest.main(verbosity=2)
