"""Behavioral replacements for operational checks previously kept in scratch/."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_support import ROOT, ensure_test_environment

ensure_test_environment()

from admin_test_support import authenticate_admin
import database
import main
from fastapi.testclient import TestClient


class OperationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_system_db()

    @classmethod
    def tearDownClass(cls):
        database.close_pg_pools()

    def setUp(self):
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_health_and_readiness(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        ready = self.client.get("/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertEqual(ready.json()["status"], "ready")

    def test_secondary_database_failure_degrades_public_readiness(self):
        original = database.get_pg_student_connection
        def fail_secondary(dbname=database.DEFAULT_EXAM_DB):
            if dbname == 'classicmodels':
                raise RuntimeError('private diagnostic detail')
            return original(dbname)
        with patch.object(database,'get_pg_student_connection',side_effect=fail_secondary):
            response = self.client.get('/ready')
        self.assertEqual(response.status_code,503)
        self.assertFalse(response.json()['checks']['classicmodels']['student'])
        self.assertNotIn('private diagnostic detail',response.text)

    def test_fixture_rejects_main_sqlite_path(self):
        with patch.dict(os.environ, {"EXAM_SQLITE_PATH": str(ROOT / "exam_system.db")}):
            with self.assertRaisesRegex(RuntimeError, "outside the disposable fixture"):
                ensure_test_environment()

    def test_fixture_rejects_wrong_cluster_identity(self):
        with patch.dict(os.environ, {"EXAM_TEST_CLUSTER": "not-the-test-cluster"}):
            with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
                ensure_test_environment()

    def test_lifespan_recovers_session_and_submission(self):
        ok, user, _ = database.login_student("RECOVERY01", "Recovery Student", "testclient", "recovery-token")
        self.assertTrue(ok)
        question = database.get_all_questions()[0]
        database.save_submission(user["id"], question["id"], "SELECT 42;", 1, 10, "correct", "Saved")
        database.set_exam_state("active")
        for _ in range(2):
            with TestClient(main.app) as client:
                self.assertEqual(client.get("/ready").status_code, 200)
                self.assertTrue(database.validate_student_session("RECOVERY01", "recovery-token", "testclient")[0])
                self.assertEqual(database.get_student_submissions(user["id"])[question["id"]]["score"], 10)
                self.assertEqual(database.get_exam_state(), "active")
        result = subprocess.run([sys.executable, "-c", "import database; "
                                 "assert database.validate_student_session('RECOVERY01', 'recovery-token', 'testclient')[0]; "
                                 f"assert database.get_student_submissions({user['id']})[{question['id']}]['score'] == 10"],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_admin_auth_and_table_viewer(self):
        endpoint = "/api/admin/table-data"
        self.assertEqual(self.client.get(endpoint, params={"db": "pagila", "table": "film"}).status_code, 403)
        authenticate_admin(self.client)
        self.assertEqual(self.client.get(endpoint, params={"db": "invalid", "table": "film"}).status_code, 400)
        for db, table in (("pagila", "film"), ("pagila", "customer"), ("classicmodels", "customers")):
            response = self.client.get(endpoint, params={"db": db, "table": table, "limit": 10, "offset": 0})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["status"], "success")
            conn = database.get_pg_admin_connection(db)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                    expected = cursor.fetchone()[0]
            finally:
                conn.close()
            self.assertGreater(expected, 0)
            self.assertEqual(result["total_rows"], expected)
            self.assertEqual(len(result["rows"]), min(10, expected))

    def test_query_limits_and_database_validation(self):
        self.assertFalse(database.execute_student_query("SELECT 1", active_db="invalid")["success"])
        self.assertFalse(database.execute_student_query("x" * (database.MAX_STUDENT_QUERY_LENGTH + 1))["success"])
        self.assertFalse(database.execute_student_query("DROP TABLE film", active_db="pagila")["success"])

    def test_concurrent_queries_return_consistent_results(self):
        query = "SELECT count(*) AS films FROM film"
        expected = database.execute_student_query(query, active_db="pagila")
        self.assertTrue(expected["success"], expected)
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(lambda _: database.execute_student_query(query, active_db="pagila"), range(36)))
        for result in results:
            self.assertTrue(result["success"], result)
            self.assertEqual(result["rows"], expected["rows"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
