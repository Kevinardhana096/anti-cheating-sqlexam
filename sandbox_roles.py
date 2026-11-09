"""PostgreSQL identities and upgrades for the application's private workspaces."""

import base64
from contextlib import closing
import hashlib
import hmac
import re
import secrets
import threading

from psycopg2 import sql

_lock = threading.RLock()
_ready = set()


def identity(nim):
    canonical = str(nim or "").strip().lower()
    if not canonical:
        raise ValueError("NIM wajib untuk sandbox pribadi.")
    digest = base64.b32encode(hashlib.sha256(canonical.encode("utf-8")).digest()).decode("ascii").rstrip("=").lower()
    return "sandbox_" + digest, "exam_s_" + digest


def credentials(nim):
    import database as db
    schema, role = identity(nim)
    with closing(db.get_sqlite_conn()) as conn, conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key='sandbox_role_secret'").fetchone()
        if row is None:
            conn.execute("INSERT OR IGNORE INTO system_settings (key,value) VALUES ('sandbox_role_secret',?)", (secrets.token_urlsafe(48),))
            row = conn.execute("SELECT value FROM system_settings WHERE key='sandbox_role_secret'").fetchone()
        secret = row[0]
    password = hmac.new(secret.encode("utf-8"), role.encode("ascii"), hashlib.sha256).hexdigest()
    return schema, role, password


def harden_role(cursor, role, password):
    import database as db
    if role == db.PG_ADMIN_USER:
        raise RuntimeError("Role mahasiswa tidak boleh sama dengan role admin PostgreSQL.")
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
    if not cursor.fetchone():
        cursor.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
    limit = 2 if role.startswith("exam_s_") else db.PG_POOL_MAXCONN * 2
    cursor.execute(sql.SQL("ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT %s PASSWORD %s").format(sql.Identifier(role)), (limit, password))
    cursor.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = %s").format(sql.Identifier(role)), ("off" if role.startswith("exam_s_") else "on",))
    cursor.execute("SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=%s", (role,))
    for membership, in cursor.fetchall():
        cursor.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(membership), sql.Identifier(role)))
    for parameter, value in (("statement_timeout", "5s"), ("lock_timeout", "3s"),
                              ("idle_in_transaction_session_timeout", "10s"), ("work_mem", "4MB"),
                              ("maintenance_work_mem", "16MB"), ("temp_file_limit", "32MB")):
        cursor.execute(sql.SQL("ALTER ROLE {} SET {} = %s").format(sql.Identifier(role), sql.Identifier(parameter)), (value,))


def _revoke_workspace(cursor, schema):
    import database as db
    for target in (sql.SQL("PUBLIC"), sql.Identifier(db.PG_STUDENT_USER)):
        cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(sql.Identifier(schema), target))
        for objects in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cursor.execute(sql.SQL("REVOKE ALL ON ALL {} IN SCHEMA {} FROM {}").format(sql.SQL(objects), sql.Identifier(schema), target))
    cursor.execute("SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname=%s AND r.rolname=%s AND c.relkind IN ('r','p','v','m','S','f') ORDER BY c.relkind='S'", (schema, db.PG_STUDENT_USER))
    for name, kind in cursor.fetchall():
        command = {"S": "SEQUENCE", "v": "VIEW", "m": "MATERIALIZED VIEW", "f": "FOREIGN TABLE"}.get(kind, "TABLE")
        cursor.execute(sql.SQL("ALTER {} {}.{} OWNER TO {}").format(sql.SQL(command), sql.Identifier(schema), sql.Identifier(name), sql.Identifier(db.PG_ADMIN_USER)))
    cursor.execute("SELECT r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname=%s", (schema,))
    if cursor.fetchone()[0] == db.PG_STUDENT_USER:
        cursor.execute(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(sql.Identifier(schema), sql.Identifier(db.PG_ADMIN_USER)))
    cursor.execute("SELECT DISTINCT r.rolname FROM pg_default_acl a JOIN pg_namespace n ON n.oid=a.defaclnamespace JOIN pg_roles r ON r.oid=a.defaclrole WHERE n.nspname=%s", (schema,))
    for owner, in cursor.fetchall():
        for objects in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} REVOKE ALL ON {} FROM PUBLIC, {}").format(sql.Identifier(owner), sql.Identifier(schema), sql.SQL(objects), sql.Identifier(db.PG_STUDENT_USER)))


def harden_database(cursor):
    import database as db
    cursor.execute("SELECT current_database()")
    dbname = cursor.fetchone()[0]
    cursor.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (dbname,))
    if cursor.fetchone()[0] == db.PG_STUDENT_USER:
        cursor.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(sql.Identifier(dbname), sql.Identifier(db.PG_ADMIN_USER)))
    cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC, {}").format(sql.Identifier(dbname), sql.Identifier(db.PG_STUDENT_USER)))
    cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(dbname), sql.Identifier(db.PG_STUDENT_USER)))
    cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'")
    schemas = [row[0] for row in cursor.fetchall()]
    for schema in schemas:
        if schema.startswith("sandbox_"):
            _revoke_workspace(cursor, schema)
            continue
        if schema.startswith("_ref_"):
            _revoke_workspace(cursor, schema)
            continue
        _revoke_workspace(cursor, schema)
        cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC, {}").format(sql.Identifier(schema), sql.Identifier(db.PG_STUDENT_USER)))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(db.PG_STUDENT_USER)))
        for objects in ("TABLES", "SEQUENCES"):
            cursor.execute(sql.SQL("REVOKE ALL ON ALL {} IN SCHEMA {} FROM PUBLIC, {}").format(sql.SQL(objects), sql.Identifier(schema), sql.Identifier(db.PG_STUDENT_USER)))
            cursor.execute(sql.SQL("GRANT SELECT ON ALL {} IN SCHEMA {} TO {}").format(sql.SQL(objects), sql.Identifier(schema), sql.Identifier(db.PG_STUDENT_USER)))
            cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} REVOKE ALL ON {} FROM PUBLIC, {}").format(sql.Identifier(schema), sql.SQL(objects), sql.Identifier(db.PG_STUDENT_USER)))
            cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON {} TO {}").format(sql.Identifier(schema), sql.SQL(objects), sql.Identifier(db.PG_STUDENT_USER)))


def ensure_workspace(nim):
    import database as db
    schema, role, password = credentials(nim)
    key = (db.PG_HOST, db.PG_PORT, db.DEFAULT_EXAM_DB, schema, password)
    with _lock:
        if key in _ready:
            return schema, role, password
    with closing(db.get_pg_admin_connection()) as conn, conn:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = 5000")
            cursor.execute("SET LOCAL lock_timeout = 3000")
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("sqlexam:database-acl:" + db.DEFAULT_EXAM_DB,))
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("sqlexam:workspace:" + schema,))
            harden_role(cursor, role, password)
            legacy = "sandbox_" + re.sub(r"[^a-zA-Z0-9_]", "", str(nim).strip()).lower()
            with closing(db.get_sqlite_conn()) as sqlite:
                users = sqlite.execute("SELECT nim FROM users").fetchall()
            legacy_owners = [row[0] for row in users if ("sandbox_" + re.sub(r"[^a-zA-Z0-9_]", "", row[0]).lower())[:63] == legacy[:63]]
            cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname IN (%s,%s)", (schema, legacy[:63]))
            existing = {row[0] for row in cursor.fetchall()}
            if legacy[:63] in existing and schema not in existing:
                if len(legacy_owners) != 1 or legacy_owners[0].lower() != str(nim).strip().lower():
                    raise RuntimeError("Sandbox lama memiliki pemilik ambigu. Pengawas harus memulihkan data sebelum melanjutkan.")
                _revoke_workspace(cursor, legacy[:63])
                cursor.execute(sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(sql.Identifier(legacy[:63]), sql.Identifier(schema)))
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            _revoke_workspace(cursor, schema)
            cursor.execute("SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s LIMIT 1", (schema,))
            if cursor.fetchone():
                raise RuntimeError("Sandbox berisi fungsi lama. Pengawas perlu memeriksanya sebelum akses dibuka.")
            cursor.execute("SELECT 1 FROM pg_operator o JOIN pg_namespace n ON n.oid=o.oprnamespace WHERE n.nspname=%s LIMIT 1", (schema,))
            if cursor.fetchone():
                raise RuntimeError("Sandbox berisi operator lama yang perlu diperiksa pengawas.")
            cursor.execute("SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=%s AND (t.typtype IN ('e','d','r','m') OR (t.typtype='b' AND t.typelem=0 AND t.typrelid=0)) LIMIT 1", (schema,))
            if cursor.fetchone():
                raise RuntimeError("Sandbox berisi tipe khusus lama yang perlu diperiksa pengawas.")
            cursor.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('v','m','f') LIMIT 1", (schema,))
            if cursor.fetchone():
                raise RuntimeError("Sandbox berisi view/foreign table lama yang perlu diperiksa pengawas.")
            cursor.execute("SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND NOT t.tgisinternal LIMIT 1", (schema,))
            if cursor.fetchone():
                raise RuntimeError("Sandbox berisi trigger lama yang perlu diperiksa pengawas.")
            cursor.execute("""SELECT 1 FROM pg_constraint f
                JOIN pg_class a ON a.oid=f.conrelid JOIN pg_namespace an ON an.oid=a.relnamespace
                JOIN pg_class b ON b.oid=f.confrelid JOIN pg_namespace bn ON bn.oid=b.relnamespace
                WHERE f.contype='f' AND an.nspname<>bn.nspname AND (an.nspname=%s OR bn.nspname=%s) LIMIT 1""", (schema, schema))
            if cursor.fetchone():
                raise RuntimeError("Sandbox memiliki relasi lintas schema yang perlu diperiksa pengawas.")
            cursor.execute("""SELECT 1 FROM pg_inherits i
                JOIN pg_class a ON a.oid=i.inhrelid JOIN pg_namespace an ON an.oid=a.relnamespace
                JOIN pg_class b ON b.oid=i.inhparent JOIN pg_namespace bn ON bn.oid=b.relnamespace
                WHERE an.nspname<>bn.nspname AND (an.nspname=%s OR bn.nspname=%s) LIMIT 1""", (schema, schema))
            if cursor.fetchone():
                raise RuntimeError("Sandbox memiliki inheritance lintas schema yang perlu diperiksa pengawas.")
            cursor.execute("SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('r','p','S') ORDER BY c.relkind='S'", (schema,))
            for name, kind in cursor.fetchall():
                cursor.execute(sql.SQL("ALTER {} {}.{} OWNER TO {}").format(sql.SQL("SEQUENCE" if kind == "S" else "TABLE"), sql.Identifier(schema), sql.Identifier(name), sql.Identifier(role)))
            cursor.execute(sql.SQL("ALTER ROLE {} SET search_path = {}").format(sql.Identifier(role), sql.Identifier(schema)))
            cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db.DEFAULT_EXAM_DB), sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT USAGE,CREATE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT ALL ON ALL SEQUENCES IN SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT ALL ON TABLES TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT ALL ON SEQUENCES TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
    with _lock:
        _ready.add(key)
    return schema, role, password


def forget_workspace(nim):
    import database as db
    schema, _ = identity(nim)
    with _lock:
        prefix = (db.PG_HOST, db.PG_PORT, db.DEFAULT_EXAM_DB, schema)
        _ready.difference_update(key for key in list(_ready) if key[:4] == prefix)


def clear_cache():
    with _lock:
        _ready.clear()
