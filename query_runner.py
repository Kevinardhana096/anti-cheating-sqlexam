"""Bounded SQL execution using restricted logins and clean master connections."""

from contextlib import closing
import datetime
import json
import math
import os
import threading
import time
import uuid

import psycopg2
from psycopg2 import sql

import sandbox_roles
from sql_policy import prepare_sql, SQLPolicyError, ParseError

QUERY_BUDGET_SECONDS = 60.0
MAX_RESPONSE_BYTES = 256 * 1024
MAX_RESULT_COLUMNS = 64
MAX_AFFECTED_ROWS = 10000
SANDBOX_MAX_CONNECTIONS = int(os.environ.get("PG_SANDBOX_MAXCONN", "20"))
_sandbox_slots = threading.BoundedSemaphore(SANDBOX_MAX_CONNECTIONS)


def _cell(value, limit):
    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float) and math.isfinite(value):
        return value, False
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        value = value.isoformat()
    elif isinstance(value, memoryview):
        truncated = len(value) > limit // 2
        return value[:limit // 2].tobytes().hex(), truncated
    else:
        value = str(value)
    return (value[:limit] + " ...[truncated]", True) if len(value) > limit else (value, False)


def execute(query_text, active_db, nim):
    import database as db
    query = (query_text or "").strip()
    active_db = (active_db or db.DEFAULT_EXAM_DB).strip().lower().split("(")[0].strip()
    if not query or len(query) > db.MAX_STUDENT_QUERY_LENGTH:
        return {"success": False, "error": "Query kosong atau melebihi batas panjang yang diizinkan."}
    if active_db not in db.ALLOWED_STUDENT_DBS:
        return {"success": False, "error": "Database target tidak valid."}
    sandbox = active_db == "sandbox_pribadi"
    try:
        schema = db.get_clean_student_schema_name(nim) if sandbox else None
        statements = prepare_sql(query, sandbox=sandbox, schema=schema)
    except SQLPolicyError as error:
        return {"success": False, "error": f"Perintah berbahaya terdeteksi: {error}"}
    except (ParseError, ValueError) as error:
        return {"success": False, "error": f"Sintaks SQL tidak valid: {error}"}

    started = time.monotonic()
    deadline = started + QUERY_BUDGET_SECONDS
    conn = None
    master_pool = None
    timer = None
    acquired_slot = False
    expired = threading.Event()
    columns, rows, affected = [], [], 0
    truncated = False
    cells_truncated = False
    virtual_changed = False
    virtual_db = None
    bytes_used = 0

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0 or expired.is_set():
            raise TimeoutError("Batas durasi total permintaan SQL terlampaui.")
        return max(1, int(seconds * 1000))

    def cancel():
        expired.set()
        try:
            conn.cancel()
        except Exception:
            pass

    try:
        if sandbox:
            if not _sandbox_slots.acquire(blocking=False):
                raise RuntimeError("Kapasitas koneksi sandbox penuh. Coba kembali sebentar lagi.")
            acquired_slot = True
            db.init_student_sandbox_schema(nim)
            _, role, password = sandbox_roles.credentials(nim)
            remaining()
            conn = psycopg2.connect(dbname=db.DEFAULT_EXAM_DB, user=role, password=password,
                                    host=db.PG_HOST, port=db.PG_PORT, connect_timeout=5)
            virtual_db = db.get_student_virtual_database(nim)
        else:
            master_pool = db.get_pg_student_pool_for_db(active_db)
            conn = db.acquire_pooled_connection(master_pool, active_db)
        conn.rollback()
        if master_pool:
            conn.autocommit = True
            with conn.cursor() as reset:
                reset.execute("DISCARD ALL")
        conn.set_session(readonly=not sandbox, autocommit=False)
        timer = threading.Timer(remaining() / 1000, cancel)
        timer.daemon = True
        timer.start()
        with conn.cursor() as control:
            control.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema or "public")))
            control.execute("SET LOCAL lock_timeout = 3000")
            for statement in statements:
                control.execute("SET LOCAL statement_timeout = %s", (remaining(),))
                if statement.kind.startswith("virtual_"):
                    name = statement.virtual_name
                    if statement.kind == "virtual_create":
                        if virtual_db and virtual_db != name:
                            raise ValueError("Hapus database virtual lama sebelum membuat nama baru.")
                        virtual_db = name
                    elif statement.kind == "virtual_use":
                        if virtual_db != name:
                            raise ValueError("Database virtual tersebut belum dibuat.")
                    else:
                        if virtual_db and virtual_db != name:
                            raise ValueError("Nama database virtual tidak sesuai.")
                        control.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s", (schema,))
                        for table, in control.fetchall():
                            control.execute("SET LOCAL statement_timeout = %s", (remaining(),))
                            control.execute(sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(sql.Identifier(schema), sql.Identifier(table)))
                        virtual_db = None
                    virtual_changed = True
                    continue
                if statement.kind == "SelectStmt":
                    with conn.cursor(name="exam_" + uuid.uuid4().hex) as result:
                        result.execute(statement.text)
                        output_rows = []
                        output_columns = None
                        while len(output_rows) <= db.MAX_RESULT_ROWS:
                            control.execute("SET LOCAL statement_timeout = %s", (remaining(),))
                            batch = result.fetchmany(min(32, db.MAX_RESULT_ROWS + 1 - len(output_rows)))
                            output_columns = [column[0] for column in result.description]
                            if len(output_columns) > MAX_RESULT_COLUMNS:
                                raise ValueError(f"Maksimal {MAX_RESULT_COLUMNS} kolom keluaran.")
                            if not batch:
                                break
                            for row in batch:
                                converted = [_cell(value, db.MAX_OUTPUT_CELL_CHARS) for value in row]
                                cells_truncated = cells_truncated or any(item[1] for item in converted)
                                values = [item[0] for item in converted]
                                size = len(json.dumps(values, ensure_ascii=True).encode("utf-8"))
                                if bytes_used + size > MAX_RESPONSE_BYTES:
                                    truncated = True
                                    break
                                bytes_used += size
                                output_rows.append(values)
                            if truncated:
                                break
                        truncated = truncated or len(output_rows) > db.MAX_RESULT_ROWS
                        columns, rows = output_columns or [], output_rows[:db.MAX_RESULT_ROWS]
                else:
                    control.execute(statement.text)
                    if control.rowcount > 0:
                        affected += control.rowcount
                        if affected > MAX_AFFECTED_ROWS:
                            raise ValueError(f"Maksimal {MAX_AFFECTED_ROWS} baris diubah per permintaan.")
                remaining()
        remaining()
        if sandbox:
            conn.commit()
            if virtual_changed:
                if virtual_db:
                    db.set_student_virtual_database(nim, virtual_db)
                else:
                    db.clear_student_virtual_database(nim)
        else:
            conn.rollback()
        row_count = len(rows) if columns else affected
        result = {"success": True, "columns": columns, "rows": rows, "row_count": row_count,
                  "is_truncated": truncated or cells_truncated, "cells_truncated": cells_truncated,
                  "execution_time_ms": round((time.monotonic() - started) * 1000, 2),
                  "message": "Query berhasil dieksekusi."}
        if sandbox:
            result["virtual_db"] = virtual_db or ""
        return result
    except (TimeoutError, psycopg2.extensions.QueryCanceledError):
        return {"success": False, "error": f"Query timeout: batas durasi total permintaan SQL {QUERY_BUDGET_SECONDS:g} detik terlampaui."}
    except Exception as error:
        return {"success": False, "error": f"PostgreSQL Error: {db.sanitize_db_error_message(error)}"}
    finally:
        reusable = True
        if timer:
            timer.cancel()
            timer.join(timeout=1)
            reusable = not timer.is_alive()
        if conn:
            if master_pool:
                try:
                    conn.rollback()
                    conn.autocommit = True
                    with conn.cursor() as cursor:
                        cursor.execute("DISCARD ALL")
                    conn.set_session(readonly=None, autocommit=False)
                except Exception:
                    reusable = False
                try:
                    master_pool.putconn(conn, close=not reusable)
                except Exception:
                    conn.close()
            else:
                conn.close()
        if acquired_slot:
            _sandbox_slots.release()
