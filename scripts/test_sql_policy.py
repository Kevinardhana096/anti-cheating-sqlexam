"""SQL parser policy tests; no database connection is required."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sql_policy import prepare_sql, split_statements, SQLPolicyError, ParseError


class SQLPolicyTests(unittest.TestCase):
    def test_split_preserves_quotes_unicode_and_nested_comments(self):
        query = "SELECT '\u00e9;\u563f'; /* a /* b; */ c */ SELECT $$hello;world$$; -- tail"
        parts = split_statements(query)
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(prepare_sql(query)), 2)

    def test_comments_and_strings_are_not_commands(self):
        self.assertEqual(len(prepare_sql("SELECT 'DROP TABLE SET ROLE', '--'; /* DROP DATABASE pagila */")), 1)

    def test_session_and_privileged_commands_are_rejected(self):
        for query in ("SET ROLE postgres", "RESET ROLE", "SET SESSION AUTHORIZATION postgres",
                      "SET statement_timeout=0", "DO $$BEGIN END$$", "COPY actor TO STDOUT",
                      "CREATE FUNCTION f() RETURNS int LANGUAGE sql AS 'SELECT 1'", "PREPARE x AS SELECT 1",
                      "SELECT set_config('statement_timeout','0',false)", "SELECT pg_catalog.pg_sleep(1)",
                      'SELECT "pg_catalog"."set_config"(\'x\',\'y\',false)', "SELECT * FROM pg_shadow"):
            with self.subTest(query=query), self.assertRaises(SQLPolicyError):
                prepare_sql(query, sandbox=True, schema="sandbox_test")

    def test_master_is_select_only_including_nested_statements(self):
        for query in ("INSERT INTO t VALUES (1)", "CREATE TABLE t(x int)", "SELECT 1 INTO t",
                      "SELECT * FROM actor FOR UPDATE", "WITH changed AS (DELETE FROM actor RETURNING *) SELECT * FROM changed"):
            with self.subTest(query=query), self.assertRaises(SQLPolicyError):
                prepare_sql(query)

    def test_functions_and_operators_are_restricted(self):
        for query in ("SELECT public.concat('a','b')", "SELECT query_to_xml('SELECT 1',false,false,'')",
                      "SELECT 1 OPERATOR(public.+) 2", "SELECT 'x'::public.custom_type"):
            with self.subTest(query=query), self.assertRaises(SQLPolicyError):
                prepare_sql(query)

    def test_functions_not_on_denylist_need_no_registration(self):
        queries=("SELECT regexp_replace('abc123','[0-9]','','g'),md5('abc'),ln(1)",
                 "SELECT to_number('12.50','99.99'),pg_catalog.pg_typeof(1)",
                 "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY x) FROM t",
                 "SELECT a_future_builtin_function(1)",
                 "SELECT 'pg_sleep(5); set_config(...)' AS text")
        for query in queries:
            for sandbox in (False,True):
                with self.subTest(query=query,sandbox=sandbox):
                    self.assertTrue(prepare_sql(query,sandbox=sandbox))

    def test_denylist_catches_qualified_quoted_nested_and_side_effect_calls(self):
        queries=("SELECT pg_catalog.pg_sleep_for('1 hour')",
                 'SELECT "pg_catalog"."set_config"(\'statement_timeout\',\'0\',false)',
                 "WITH x AS (SELECT pg_advisory_lock(1)) SELECT * FROM x",
                 "SELECT pg_try_advisory_xact_lock(1)",
                 "SELECT pg_cancel_backend(pg_backend_pid())",
                 "SELECT pg_read_binary_file('/tmp/secret')",
                 "SELECT lo_import('/tmp/secret')",
                 "SELECT dblink_exec('connection','DROP TABLE t')",
                 "SELECT query_to_xml('SELECT pg_sleep(1)',false,false,'')",
                 "SELECT ts_rewrite('a','SELECT a,b FROM t')",
                 "SELECT pg_stat_get_activity(NULL)",
                 "SELECT pg_notify('exam','message')")
        for query in queries:
            for sandbox in (False,True):
                with self.subTest(query=query,sandbox=sandbox),self.assertRaises(SQLPolicyError):
                    prepare_sql(query,sandbox=sandbox)

    def test_execution_and_reference_determinism_are_separate(self):
        from grading_engine import reference_statements
        for query in ('SELECT random()', 'SELECT clock_timestamp()', 'SELECT gen_random_uuid()'):
            with self.subTest(query=query):
                self.assertTrue(prepare_sql(query))
                with self.assertRaises(ValueError):
                    reference_statements(query,False)

    def test_supported_query_and_ddl(self):
        self.assertTrue(prepare_sql("WITH x AS (SELECT 1 n) SELECT round(avg(n),2) FROM x"))
        self.assertTrue(prepare_sql("CREATE TABLE t(id SERIAL PRIMARY KEY, n VARCHAR(50)); INSERT INTO t(n) VALUES('abc'); ALTER TABLE t ADD COLUMN age INT; SELECT * FROM t; DROP TABLE t", sandbox=True, schema="sandbox_test"))

    def test_extract_date_aggregate_report_is_allowed_in_both_modes(self):
        query = """SELECT DATE_part('month', p.payment_date) AS bulan,
            UPPER(c.name) AS kategori, COUNT(p.payment_id) AS jumlah_pembayaran,
            SUM(p.amount) AS total_pendapatan,
            round(AVG(p.amount), 2) AS rata_rata_pembayaran
            FROM payment p JOIN rental r ON r.rental_id=p.rental_id
            JOIN inventory i ON i.inventory_id=r.inventory_id
            JOIN film f ON f.film_id=i.film_id
            JOIN film_category fc ON fc.film_id=f.film_id
            JOIN category c ON c.category_id=fc.category_id
            WHERE EXTRACT(YEAR FROM p.payment_date)=2025
            GROUP BY DATE_part('month',p.payment_date),c.name
            ORDER BY bulan,total_pendapatan DESC"""
        for sandbox in (False,True):
            with self.subTest(sandbox=sandbox):
                self.assertTrue(prepare_sql(query,sandbox=sandbox))
                self.assertTrue(prepare_sql("SELECT EXTRACT(MONTH FROM TIMESTAMP '2025-03-01')",sandbox=sandbox))
                with self.assertRaises(SQLPolicyError):
                    prepare_sql("SELECT public.extract('year',CURRENT_TIMESTAMP)",sandbox=sandbox)

    def test_explicit_other_schema_is_rejected(self):
        for query in ("SELECT * FROM sandbox_other.t", "CREATE TABLE public.t(x int)", "DROP TABLE sandbox_other.t"):
            with self.subTest(query=query), self.assertRaises(SQLPolicyError):
                prepare_sql(query, sandbox=True, schema="sandbox_test")

    def test_virtual_commands_are_exact_and_keep_use_statement(self):
        result = prepare_sql("/* start */ CREATE DATABASE mydb; USE mydb; DROP DATABASE mydb", sandbox=True)
        self.assertEqual([item.kind for item in result], ["virtual_create", "virtual_use", "virtual_drop"])
        for query in ("DROP DATABASE pagila", "CREATE DATABASE abc WITH OWNER postgres", "USE abc ignored_tail"):
            with self.subTest(query=query), self.assertRaises((SQLPolicyError, ParseError)):
                prepare_sql(query, sandbox=True)

    def test_statement_limit_and_empty_comments(self):
        with self.assertRaises(SQLPolicyError):
            prepare_sql("SELECT 1;" * 21)
        with self.assertRaises(ValueError):
            prepare_sql("-- comment only")


if __name__ == "__main__":
    unittest.main(verbosity=2)
