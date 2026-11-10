"""Open audit findings: expected failures must be removed when the behavior is fixed."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment

ensure_test_environment()

import database
import main
from fastapi.testclient import TestClient


class KnownRisksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_system_db()

    def setUp(self):
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def test_phase2_waiting_state_blocks_query_api(self):
        database.login_student("RISKWAIT", "Waiting Student", "testclient", "risk-token")
        database.set_exam_state("waiting")
        with patch.object(database, "execute_student_query", return_value={"success": True}):
            response = self.client.post("/api/student/run-query", json={
                "nim": "RISKWAIT", "session_token": "risk-token", "query": "SELECT 1"})
        self.assertEqual(response.status_code, 403)

    def test_phase2_shared_ip_does_not_allow_session_takeover(self):
        database.login_student("RISKDEVICE", "Device Student", "testclient", "first", "device-a")
        ok, _, _ = database.login_student("RISKDEVICE", "Device Student", "testclient", "second", "device-b")
        self.assertFalse(ok)

    def test_phase3_nim_schema_names_do_not_collide(self):
        self.assertNotEqual(database.get_clean_student_schema_name("AB-12"),
                            database.get_clean_student_schema_name("ab.12"))

    def test_phase4_rows_beyond_preview_limit_are_compared(self):
        result = database.evaluate_sql_submission(
            "SELECT n FROM generate_series(1,501) n",
            "SELECT n FROM generate_series(1,502) n", target_db="pagila", active_db="pagila")
        self.assertFalse(result["is_correct"])

    def test_phase4_text_codes_preserve_leading_zeroes(self):
        self.assertNotEqual(database._normalize_cell_value("001"), database._normalize_cell_value("1"))

    def test_phase5_invalid_session_cannot_append_log(self):
        response = self.client.post("/api/student/log-event", json={
            "nim": "NOT_REGISTERED", "session_token": "invalid", "action_type": "blur_tab"})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
