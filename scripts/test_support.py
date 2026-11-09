"""Disposable SQLite and PostgreSQL fixtures shared by regression scripts."""

import atexit
from contextlib import ExitStack, contextmanager
import glob
import importlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
_stack = ExitStack()


def close_standalone_fixture():
    try:
        _stack.close()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


def postgres_bin():
    suffix = ".exe" if os.name == "nt" else ""
    candidates = []
    if os.environ.get("TEST_PG_BIN"):
        candidates.append(Path(os.environ["TEST_PG_BIN"]))
    executable = shutil.which("initdb")
    if executable:
        candidates.append(Path(executable).parent)
    for pattern in (
        "C:/Program Files/PostgreSQL/*/bin", "/usr/lib/postgresql/*/bin",
        "/opt/homebrew/opt/postgresql*/bin", "/usr/local/opt/postgresql*/bin",
    ):
        candidates.extend(Path(p) for p in sorted(glob.glob(pattern), reverse=True))
    for candidate in candidates:
        if all((candidate / (name + suffix)).is_file() for name in ("initdb", "pg_ctl")):
            return candidate
    raise RuntimeError("PostgreSQL tools not found. Set TEST_PG_BIN to the directory containing initdb and pg_ctl.")


def run_command(command, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    output = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if command[-1] == "start" else {"capture_output": True}
    return subprocess.run(command, check=True, **output, text=True,
                          encoding="utf-8", errors="replace", timeout=120, **kwargs)


@contextmanager
def isolated_environment(postgres=True):
    previous = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="sqlexam_tests_") as directory:
        root = Path(directory)
        os.environ.update({
            "EXAM_TEST_ROOT": str(root), "EXAM_SQLITE_PATH": str(root / "exam.db"),
            "ADMIN_MASTER_KEY": "test-admin-only", "ALLOW_SHARED_IP": "true",
            "EXAM_HINT_MODE": "strict", "DEFAULT_EXAM_DB": "pagila", "PG_DB": "pagila",
        })
        pg_ctl = None
        data = root / "postgres"
        try:
            if postgres:
                binaries = postgres_bin()
                suffix = ".exe" if os.name == "nt" else ""
                pg_ctl = str(binaries / ("pg_ctl" + suffix))
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                cluster = "sqlexam_test_" + uuid.uuid4().hex
                os.environ.update({
                    "PG_HOST": "127.0.0.1", "PG_PORT": str(port), "PG_ADMIN_USER": "postgres",
                    "PG_ADMIN_PASS": "", "PG_STUDENT_USER": "student_role",
                    "PG_STUDENT_PASS": "test-student-only", "PG_POOL_MAXCONN": "50",
                    "EXAM_TEST_CLUSTER": cluster,
                })
                run_command([str(binaries / ("initdb" + suffix)), "-D", str(data),
                             "-U", "postgres", "--auth=trust", "--encoding=UTF8", "--locale=C"])
                with (data / "postgresql.conf").open("a", encoding="utf-8") as config:
                    config.write(f"\nlisten_addresses = '127.0.0.1'\nport = {port}\n"
                                 f"cluster_name = '{cluster}'\nfsync = off\n"
                                 "synchronous_commit = off\nmax_connections = 120\n")
                    if os.name != "nt":
                        config.write(f"unix_socket_directories = '{root.as_posix()}'\n")
                run_command([pg_ctl, "-D", str(data), "-l", str(root / "postgres.log"), "-w", "start"])
                bootstrap_databases()
            yield root
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Test fixture command failed: {error.stdout}\n{error.stderr}") from error
        finally:
            module = sys.modules.get("database")
            if module:
                module.close_pg_pools()
            try:
                if pg_ctl and (data / "postmaster.pid").exists():
                    run_command([pg_ctl, "-D", str(data), "-m", "immediate", "-w", "stop"])
            finally:
                os.environ.clear()
                os.environ.update(previous)


def bootstrap_databases():
    import psycopg2
    from psycopg2 import sql
    conn = psycopg2.connect(dbname="postgres", host=os.environ["PG_HOST"],
                            port=os.environ["PG_PORT"], user="postgres")
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            for name in ("pagila", "classicmodels"):
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        conn.close()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    database = importlib.import_module("database")
    database.init_system_db()
    ok, message = database.init_postgres_db()
    if not ok:
        raise RuntimeError(message)
    ok, message = database.reset_target_database("classicmodels")
    if not ok:
        raise RuntimeError(message)


def ensure_test_environment():
    """Direct test invocation creates a fixture; runner children verify its identity."""
    if not os.environ.get("EXAM_TEST_ROOT"):
        _stack.enter_context(isolated_environment())
        atexit.register(close_standalone_fixture)
    root = Path(os.environ["EXAM_TEST_ROOT"]).resolve()
    sqlite = Path(os.environ["EXAM_SQLITE_PATH"]).resolve()
    if root not in sqlite.parents or not (root / "postgres" / "PG_VERSION").is_file():
        raise RuntimeError("Refusing to run tests outside the disposable fixture.")
    import psycopg2
    conn = psycopg2.connect(dbname="postgres", host=os.environ["PG_HOST"],
                            port=os.environ["PG_PORT"], user=os.environ["PG_ADMIN_USER"],
                            connect_timeout=5)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW cluster_name")
            if cursor.fetchone()[0] != os.environ["EXAM_TEST_CLUSTER"]:
                raise RuntimeError("PostgreSQL test cluster identity mismatch.")
    finally:
        conn.close()
    database = importlib.import_module("database")
    database.init_system_db()
    if not database._HARDENED_DATABASES:
        ok, message = database.init_postgres_db()
        if not ok:
            raise RuntimeError(message)
