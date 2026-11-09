"""Privilege and execution-boundary checks against a disposable PostgreSQL cluster."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment

ensure_test_environment()

import database
import query_runner
import sandbox_roles
import sql_policy
import psycopg2
from psycopg2 import sql


class SandboxSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = "SECURITY_A", "SECURITY_B"
        for nim in (cls.a, cls.b):
            database.login_student(nim, nim, "testclient", "token_" + nim, "dev_" + nim)
            database.init_student_sandbox_schema(nim)
        cls.schema_a = database.get_clean_student_schema_name(cls.a)
        cls.schema_b = database.get_clean_student_schema_name(cls.b)
        result = database.execute_student_query("CREATE TABLE secret (id INT PRIMARY KEY, value TEXT); INSERT INTO secret VALUES(1,'private-a')", "sandbox_pribadi", cls.a)
        if not result["success"]:
            raise RuntimeError(result["error"])

    @classmethod
    def tearDownClass(cls):
        for nim in (cls.a, cls.b):
            database.cleanup_student_sandbox_schema(nim)
        database.close_pg_pools()

    def raw_connection(self, nim):
        _, role, password = sandbox_roles.ensure_workspace(nim)
        return psycopg2.connect(dbname=database.DEFAULT_EXAM_DB, user=role, password=password,
                                host=database.PG_HOST, port=database.PG_PORT, connect_timeout=5)

    def admin(self, query, params=None):
        with closing(database.get_pg_admin_connection()) as conn, conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall() if cursor.description else []

    def test_logins_are_individual_and_have_no_privileged_attributes(self):
        for nim in (self.a, self.b):
            _, role = sandbox_roles.identity(nim)
            with closing(self.raw_connection(nim)) as conn, conn, conn.cursor() as cursor:
                cursor.execute("SELECT current_user,session_user")
                self.assertEqual(cursor.fetchone(), (role, role))
                cursor.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit FROM pg_roles WHERE rolname=current_user")
                self.assertEqual(cursor.fetchone(), (False,) * 6)

    def test_raw_role_cannot_read_or_modify_another_workspace(self):
        for statement in (
            f"SELECT * FROM {self.schema_a}.secret",
            f"INSERT INTO {self.schema_a}.secret VALUES(2,'bad')",
            f"UPDATE {self.schema_a}.secret SET value='bad' WHERE false",
            f"DELETE FROM {self.schema_a}.secret WHERE false",
            f"DROP TABLE {self.schema_a}.secret",
            f"TRUNCATE {self.schema_a}.secret",
            f"ALTER TABLE {self.schema_a}.secret ADD COLUMN bad INT",
            f"CREATE TABLE {self.schema_a}.bad(id INT)",
        ):
            with self.subTest(statement=statement), closing(self.raw_connection(self.b)) as conn:
                with conn.cursor() as cursor, self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    cursor.execute(statement)
        self.assertEqual(self.admin(sql.SQL("SELECT value FROM {}.secret").format(sql.Identifier(self.schema_a))), [("private-a",)])

    def test_search_path_and_set_config_cannot_grant_access(self):
        with closing(self.raw_connection(self.b)) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('search_path',%s,false)", (self.schema_a,))
                with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    cursor.execute(sql.SQL("SELECT * FROM {}.secret").format(sql.Identifier(self.schema_a)))

    def test_reset_role_does_not_reveal_admin_and_set_role_is_denied(self):
        with closing(self.raw_connection(self.b)) as conn:
            with conn.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT current_user=session_user")
                self.assertTrue(cursor.fetchone()[0])
                for role in (database.PG_ADMIN_USER, database.PG_STUDENT_USER, sandbox_roles.identity(self.a)[1]):
                    with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
                    conn.rollback()

    def test_shared_master_login_has_no_workspace_access(self):
        with closing(database.get_pg_student_connection()) as conn, conn.cursor() as cursor:
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute(sql.SQL("SELECT * FROM {}.secret").format(sql.Identifier(self.schema_a)))

    def test_master_privilege_blocks_writes_even_with_readonly_disabled(self):
        with closing(database.get_pg_student_connection()) as conn:
            conn.set_session(readonly=False)
            with conn.cursor() as cursor, self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute("DELETE FROM public.actor WHERE false")

    def test_sandbox_role_cannot_write_master_or_create_temp_table(self):
        for statement in ("INSERT INTO public.actor(actor_id,first_name,last_name) VALUES(999999,'bad','bad')",
                          "CREATE TEMP TABLE bad_temp(x int)", "CREATE ROLE bad_role", "CREATE DATABASE bad_database"):
            with self.subTest(statement=statement), closing(self.raw_connection(self.b)) as conn:
                conn.autocommit = True
                with conn.cursor() as cursor, self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    cursor.execute(statement)

    def test_private_role_cannot_connect_to_other_master_database(self):
        _, role, password = sandbox_roles.credentials(self.b)
        with self.assertRaises(psycopg2.OperationalError):
            with closing(psycopg2.connect(dbname="classicmodels", user=role, password=password,
                                          host=database.PG_HOST, port=database.PG_PORT, connect_timeout=5)):
                pass

    def test_api_rejects_control_commands_before_connecting(self):
        for query in ("RESET ROLE", "SET statement_timeout=0", "SELECT set_config('statement_timeout','0',false)",
                      "DO $$BEGIN END$$", "COPY actor TO STDOUT", "CREATE FUNCTION f() RETURNS int LANGUAGE sql AS 'SELECT 1'"):
            with self.subTest(query=query), patch.object(database.psycopg2, "connect") as connect:
                result = database.execute_student_query(query, "sandbox_pribadi", self.a)
                self.assertFalse(result["success"])
                connect.assert_not_called()

    def test_failed_student_connection_never_uses_admin_fallback(self):
        original = psycopg2.connect
        role = sandbox_roles.identity(self.a)[1]
        def fail_student(*args, **kwargs):
            if kwargs.get("user") == role:
                raise psycopg2.OperationalError("authentication failed")
            return original(*args, **kwargs)
        with patch.object(database.psycopg2, "connect", side_effect=fail_student), patch.object(database, "get_pg_admin_connection") as admin:
            result = database.execute_student_query("SELECT 1", "sandbox_pribadi", self.a)
        self.assertFalse(result["success"])
        admin.assert_not_called()

    def test_script_is_atomic_when_a_later_statement_fails(self):
        result = database.execute_student_query("CREATE TABLE atomic_failure(x INT); INSERT INTO atomic_failure VALUES(1); SELECT 1/0", "sandbox_pribadi", self.b)
        self.assertFalse(result["success"])
        self.assertEqual(self.admin("SELECT to_regclass(%s)", (self.schema_b + ".atomic_failure",)), [(None,)])

    def test_entire_script_is_validated_before_first_statement(self):
        result = database.execute_student_query("CREATE TABLE policy_failure(x INT); RESET ROLE", "sandbox_pribadi", self.b)
        self.assertFalse(result["success"])
        self.assertEqual(self.admin("SELECT to_regclass(%s)", (self.schema_b + ".policy_failure",)), [(None,)])

    def test_virtual_database_emulation_commits_and_rolls_back(self):
        result = database.execute_student_query("CREATE DATABASE test_virtual; USE test_virtual; CREATE TABLE virtual_table(x INT)", "sandbox_pribadi", self.b)
        self.assertTrue(result["success"], result)
        self.assertEqual(database.get_student_virtual_database(self.b), "test_virtual")
        failed = database.execute_student_query("DROP DATABASE test_virtual; SELECT 1/0", "sandbox_pribadi", self.b)
        self.assertFalse(failed["success"])
        self.assertEqual(database.get_student_virtual_database(self.b), "test_virtual")
        result = database.execute_student_query("DROP DATABASE test_virtual", "sandbox_pribadi", self.b)
        self.assertTrue(result["success"], result)
        self.assertIsNone(database.get_student_virtual_database(self.b))

    def test_total_deadline_applies_across_statements(self):
        prefixes=tuple(p for p in sql_policy.BLOCKED_FUNCTION_PREFIXES if p!='pg_sleep')
        with patch.object(sql_policy, "BLOCKED_FUNCTION_PREFIXES", prefixes), patch.object(query_runner, "QUERY_BUDGET_SECONDS", 0.25):
            started = time.monotonic()
            result = database.execute_student_query("SELECT pg_sleep(0.12); SELECT pg_sleep(0.12); SELECT pg_sleep(0.12)", "pagila")
        self.assertFalse(result["success"], result)
        self.assertIn("timeout", result["error"].lower())
        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(database.execute_student_query("SELECT 1", "pagila")["success"])

    def test_function_denylist_allows_general_builtins_on_real_connections(self):
        query="SELECT regexp_replace('abc123','[0-9]','','g') AS txt, to_number('12.50','99.99') AS n, md5('abc') AS digest, pg_typeof(1)::text AS kind"
        for target in ('pagila','sandbox_pribadi'):
            with self.subTest(target=target):
                result=database.execute_student_query(query,target,self.b)
                self.assertTrue(result['success'],result)
                self.assertEqual(result['rows'][0][0],'abc')
                self.assertEqual(result['rows'][0][3],'integer')
                denied=database.execute_student_query("SELECT query_to_xml('SELECT pg_sleep(1)',false,false,'')",target,self.b)
                self.assertFalse(denied['success'],denied)
                self.assertIn('dilarang',denied['error'])

    def test_master_connection_is_reset_before_and_after_reuse(self):
        pool = database.get_pg_student_pool_for_db("pagila")
        conn = database.acquire_pooled_connection(pool)
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute("SET application_name='poisoned'; SET work_mem='16MB'; SELECT pg_advisory_lock(989898)")
        pool.putconn(conn)
        self.assertTrue(database.execute_student_query("SELECT 1", "pagila")["success"])
        conn = database.acquire_pooled_connection(pool)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW application_name")
                self.assertNotEqual(cursor.fetchone()[0], "poisoned")
                cursor.execute("SHOW work_mem")
                self.assertEqual(cursor.fetchone()[0], "4MB")
                cursor.execute("SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'")
                self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            conn.rollback()
            pool.putconn(conn)

    def test_cell_and_response_limits_apply_to_both_execution_paths(self):
        for target in ("pagila", "sandbox_pribadi"):
            with self.subTest(target=target):
                result = database.execute_student_query("SELECT '" + "x" * 5000 + "' AS data", target, self.a)
                self.assertTrue(result["success"], result)
                self.assertTrue(result["cells_truncated"])
                self.assertLess(len(result["rows"][0][0]), 4100)
                result = database.execute_student_query("SELECT n, '" + "x" * 3900 + "' AS data FROM generate_series(1,10000) n", target, self.a)
                self.assertTrue(result["success"], result)
                self.assertTrue(result["is_truncated"])
                self.assertLessEqual(len(json.dumps(result["rows"]).encode()), query_runner.MAX_RESPONSE_BYTES + 1000)
                self.assertLess(len(result["rows"]), 100)

    def test_column_limit_returns_controlled_error(self):
        result = database.execute_student_query("SELECT " + ",".join(f"{i} AS col{i}" for i in range(65)), "pagila")
        self.assertFalse(result["success"])
        self.assertIn("64", result["error"])

    def test_write_row_limit_rolls_back_the_entire_script(self):
        result = database.execute_student_query("CREATE TABLE too_many(x INT); INSERT INTO too_many SELECT n FROM generate_series(1,10001) n", "sandbox_pribadi", self.b)
        self.assertFalse(result["success"])
        self.assertEqual(self.admin("SELECT to_regclass(%s)", (self.schema_b + ".too_many",)), [(None,)])

    def test_capacity_rejection_does_not_open_an_admin_connection(self):
        with patch.object(query_runner, "_sandbox_slots", threading.BoundedSemaphore(0)), patch.object(database, "get_pg_admin_connection") as admin:
            result = database.execute_student_query("SELECT 1", "sandbox_pribadi", self.a)
        self.assertFalse(result["success"])
        admin.assert_not_called()

    def test_full_hash_names_are_stable_and_fit_postgres_identifiers(self):
        first = sandbox_roles.identity("A" * 200 + "-1")
        second = sandbox_roles.identity("A" * 200 + ".1")
        self.assertNotEqual(first, second)
        self.assertEqual(first, sandbox_roles.identity("a" * 200 + "-1"))
        self.assertTrue(all(len(name) <= 63 for name in first))

    def test_cleanup_removes_schema_role_and_allows_fresh_provision(self):
        nim = "SECURITY_CLEANUP"
        self.assertTrue(database.execute_student_query("CREATE TABLE to_remove(id SERIAL)", "sandbox_pribadi", nim)["success"])
        schema, role = sandbox_roles.identity(nim)
        self.assertTrue(database.cleanup_student_sandbox_schema(nim))
        self.assertEqual(self.admin("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (schema,)), [(0,)])
        self.assertEqual(self.admin("SELECT count(*) FROM pg_roles WHERE rolname=%s", (role,)), [(0,)])
        self.assertTrue(database.execute_student_query("CREATE TABLE fresh(id INT)", "sandbox_pribadi", nim)["success"])
        self.assertTrue(database.cleanup_student_sandbox_schema(nim))

    def test_individual_reset_preserves_sqlite_when_pg_cleanup_fails(self):
        nim = "RESET_FAILURE_SECURITY"
        ok, user, _ = database.login_student(nim, nim, "testclient", nim + "token", nim + "device")
        self.assertTrue(ok)
        database.init_student_sandbox_schema(nim)
        role = sandbox_roles.identity(nim)[1]
        question = database.get_all_questions()[0]
        database.save_submission(user["id"], question["id"], "SELECT 1", 1, 5)
        self.admin(sql.SQL("GRANT SELECT ON public.actor TO {}").format(sql.Identifier(role)))
        try:
            self.assertFalse(database.reset_student_by_nim(nim)["success"])
            self.assertEqual(database.get_student_submissions(user["id"])[question["id"]]["score"], 5)
            self.assertTrue(database.validate_student_session(nim, nim + "token", "testclient")[0])
        finally:
            self.admin(sql.SQL("REVOKE SELECT ON public.actor FROM {}").format(sql.Identifier(role)))
        self.assertTrue(database.reset_student_by_nim(nim)["success"])

    def test_credentials_survive_cache_clear(self):
        original = sandbox_roles.credentials(self.a)
        sandbox_roles.clear_cache()
        self.assertTrue(original == sandbox_roles.credentials(self.a))
        self.assertTrue(database.execute_student_query("SELECT 1", "sandbox_pribadi", self.a)["success"])

    def test_legacy_schema_upgrade_preserves_data_and_changes_owner(self):
        nim, legacy = "LEGACY-SECURITY", "sandbox_legacysecurity"
        database.login_student(nim, nim, "testclient", "legacy-token", "legacy-device")
        with closing(database.get_pg_admin_connection()) as conn, conn, conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}; CREATE TABLE {}.saved(id SERIAL); INSERT INTO {}.saved VALUES(42)").format(*[sql.Identifier(legacy)] * 3))
            cursor.execute(sql.SQL("ALTER TABLE {}.saved OWNER TO {}").format(sql.Identifier(legacy), sql.Identifier(database.PG_STUDENT_USER)))
            database.grant_student_permissions(cursor)
        result = database.execute_student_query("SELECT * FROM saved", "sandbox_pribadi", nim)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["rows"], [[42]])
        serial = database.execute_student_query("INSERT INTO saved DEFAULT VALUES; SELECT id FROM saved ORDER BY id", "sandbox_pribadi", nim)
        self.assertTrue(serial["success"], serial)
        self.assertEqual(serial["rows"], [[1], [42]])
        self.assertTrue(database.execute_student_query("DROP TABLE saved", "sandbox_pribadi", nim)["success"])
        self.assertTrue(database.cleanup_student_sandbox_schema(nim))

    def test_hardening_removes_legacy_master_table_ownership(self):
        with closing(database.get_pg_admin_connection()) as conn, conn, conn.cursor() as cursor:
            cursor.execute("CREATE TABLE public.legacy_owned_table(x INT)")
            cursor.execute(sql.SQL("ALTER TABLE public.legacy_owned_table OWNER TO {}").format(sql.Identifier(database.PG_STUDENT_USER)))
            database.grant_student_permissions(cursor)
        try:
            with closing(database.get_pg_student_connection()) as conn:
                conn.set_session(readonly=False)
                with conn.cursor() as cursor, self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    cursor.execute("DELETE FROM public.legacy_owned_table WHERE false")
        finally:
            self.admin("DROP TABLE public.legacy_owned_table")

    def test_ambiguous_legacy_schema_is_preserved_and_sealed(self):
        for nim in ("COLLISION-SECURITY", "COLLISION.SECURITY"):
            database.login_student(nim, nim, "testclient", nim + "-token", nim + "-device")
        legacy = "sandbox_collisionsecurity"
        with closing(database.get_pg_admin_connection()) as conn, conn, conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}; CREATE TABLE {}.saved(id INT)").format(sql.Identifier(legacy), sql.Identifier(legacy)))
            database.grant_student_permissions(cursor)
        with self.assertRaisesRegex(RuntimeError, "ambigu"):
            database.init_student_sandbox_schema("COLLISION-SECURITY")
        self.assertEqual(self.admin("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (legacy,)), [(1,)])
        with closing(database.get_pg_student_connection()) as conn, conn.cursor() as cursor:
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute(sql.SQL("SELECT * FROM {}.saved").format(sql.Identifier(legacy)))
        self.admin(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(legacy)))

    def test_legacy_functions_prevent_automatic_workspace_upgrade(self):
        nim, legacy = "FUNCTION-SECURITY", "sandbox_functionsecurity"
        database.login_student(nim, nim, "testclient", "function-token", "function-device")
        with closing(database.get_pg_admin_connection()) as conn, conn, conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}; CREATE FUNCTION {}.old_function() RETURNS int LANGUAGE sql AS 'SELECT 1'").format(sql.Identifier(legacy), sql.Identifier(legacy)))
            database.grant_student_permissions(cursor)
        with self.assertRaisesRegex(RuntimeError, "fungsi lama"):
            database.init_student_sandbox_schema(nim)
        self.assertEqual(self.admin("SELECT count(*) FROM pg_namespace WHERE nspname=%s", (legacy,)), [(1,)])
        self.admin(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(legacy)))

    def test_concurrent_sandboxes_keep_distinct_data(self):
        def worker(index):
            nim = f"PARALLEL_SECURITY_{index}"
            result = database.execute_student_query(f"CREATE TABLE own_data(id INT); INSERT INTO own_data VALUES({index}); SELECT * FROM own_data", "sandbox_pribadi", nim)
            try:
                self.assertTrue(result["success"], result)
                self.assertEqual(result["rows"], [[index]])
                return True
            finally:
                database.cleanup_student_sandbox_schema(nim)
        with ThreadPoolExecutor(max_workers=4) as executor:
            self.assertTrue(all(executor.map(worker, range(4))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
