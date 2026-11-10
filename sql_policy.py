"""Parse the supported exam SQL subset before any statement is executed."""

from dataclasses import dataclass
import re

from pglast import parse_sql, scan
from pglast.parser import ParseError


MAX_STATEMENTS = 20
BLOCKED_FUNCTIONS = frozenset("""
    set_config pg_cancel_backend pg_terminate_backend pg_reload_conf pg_rotate_logfile
    pg_log_backend_memory_contexts pg_promote pg_switch_wal pg_create_restore_point
    pg_wal_replay_pause pg_wal_replay_resume pg_export_snapshot pg_notify
    pg_import_system_collations pg_sync_replication_slots
    pg_walsummary_contents pg_get_wal_resource_managers
    loread lowrite ts_rewrite
""".split())
BLOCKED_FUNCTION_PREFIXES = (
    "pg_sleep", "pg_advisory_", "pg_try_advisory_", "pg_read_", "pg_write_", "pg_file_", "pg_ls_",
    "pg_stat_", "pg_backup_", "pg_start_backup", "pg_stop_backup", "pg_logical_", "pg_replication_",
    "pg_create_physical_replication_", "pg_create_logical_replication_", "pg_drop_replication_",
    "pg_copy_physical_replication_", "pg_copy_logical_replication_", "pg_replication_origin_",
    "pg_show_replication_", "pg_get_replication_", "binary_upgrade_", "lo_", "dblink",
    "query_to_xml", "cursor_to_xml", "table_to_xml", "schema_to_xml", "database_to_xml",
)

# Execution may allow these; retrying a stored answer must not change its context.
NON_REPLAYABLE_FUNCTIONS = frozenset("""
    now transaction_timestamp statement_timestamp clock_timestamp timeofday
    random random_normal setseed gen_random_uuid uuidv4 uuidv7
    nextval currval lastval setval current_setting current_query pg_backend_pid
    txid_current pg_current_xact_id
""".split())
SAFE_TYPES = set("""
    int2 int4 int8 smallint integer bigint serial smallserial bigserial serial2 serial4 serial8
    numeric decimal real float4 float8 double float boolean bool char bpchar varchar text
    date time timetz timestamp timestamptz interval uuid json jsonb bytea money bit varbit
    regclass oid record name void
""".split())
SANDBOX_STATEMENTS = {"SelectStmt", "CreateStmt", "CreateTableAsStmt", "InsertStmt",
                      "UpdateStmt", "DeleteStmt", "TruncateStmt", "DropStmt", "IndexStmt", "AlterTableStmt"}
ALTER_COMMANDS = {"AT_AddColumn", "AT_DropColumn", "AT_AlterColumnType", "AT_SetNotNull",
                  "AT_DropNotNull", "AT_AddConstraint", "AT_DropConstraint", "AT_ColumnDefault"}


class SQLPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ExamStatement:
    text: str
    kind: str
    virtual_name: str = ""


def split_statements(query):
    data = query
    start = 0
    result = []
    for token in scan(query):
        if token.name == "ASCII_59":
            result.append(data[start:token.start].strip())
            start = token.end + 1
    result.append(data[start:].strip())
    return [part for part in result if any(t.name not in ("C_COMMENT", "SQL_COMMENT") for t in scan(part))]


def without_comments(query):
    data = list(query)
    for token in scan(query):
        if token.name in ("C_COMMENT", "SQL_COMMENT"):
            data[token.start:token.end + 1] = " " * (token.end - token.start + 1)
    return "".join(data).strip()


def _walk(node):
    stack = [(node, 0)]
    count = 0
    while stack:
        current, depth = stack.pop()
        if depth > 64:
            raise SQLPolicyError("Struktur SQL terlalu dalam.")
        if isinstance(current, dict):
            count += 1
            if count > 4096:
                raise SQLPolicyError("Struktur SQL terlalu kompleks.")
            yield current
            stack.extend((value, depth + 1) for value in current.values() if isinstance(value, (dict, tuple, list)))
        elif isinstance(current, (tuple, list)):
            stack.extend((value, depth + 1) for value in current)


def _names(values):
    return [value["sval"] for value in values or ()]


def prepare_sql(query, sandbox=False, schema=None):
    parts = split_statements(query)
    if not parts:
        raise ValueError("Query SQL tidak boleh kosong.")
    if len(parts) > MAX_STATEMENTS:
        raise SQLPolicyError(f"Maksimal {MAX_STATEMENTS} statement per permintaan.")
    result = []
    for part in parts:
        clean = without_comments(part)
        virtual = re.fullmatch(r"(CREATE\s+DATABASE(?:\s+IF\s+NOT\s+EXISTS)?|DROP\s+DATABASE(?:\s+IF\s+EXISTS)?|USE)\s+([A-Za-z_][A-Za-z0-9_]*)", clean, re.I)
        if sandbox and virtual:
            verb = virtual[1].split()[0].upper()
            name = virtual[2].lower()
            if name in {"postgres", "pagila", "classicmodels", "praktikum_db", "template0", "template1"}:
                raise SQLPolicyError("Nama database sistem tidak boleh dipakai untuk database virtual.")
            result.append(ExamStatement(part, "virtual_" + verb.lower(), name))
            continue
        roots = parse_sql(part)
        if len(roots) != 1:
            raise SQLPolicyError("Statement SQL tidak valid.")
        try:
            tree = roots[0].stmt()
        except RecursionError as error:
            raise SQLPolicyError("Struktur SQL terlalu dalam.") from error
        allowed = SANDBOX_STATEMENTS if sandbox else {"SelectStmt"}
        for node in _walk(tree):
            kind = node.get("@", "")
            if kind.endswith("Stmt") and kind not in allowed:
                raise SQLPolicyError(f"Perintah {kind} tidak diizinkan.")
            if kind == "SelectStmt" and (node.get("intoClause") or node.get("lockingClause")):
                raise SQLPolicyError("SELECT INTO dan penguncian baris tidak diizinkan.")
            if kind in {"InsertStmt", "UpdateStmt", "DeleteStmt"} and node.get("returningClause"):
                raise SQLPolicyError("Gunakan SELECT terpisah untuk melihat hasil DML.")
            if kind == "CommonTableExpr" and node["ctequery"].get("@") != "SelectStmt":
                raise SQLPolicyError("CTE hanya boleh berisi SELECT.")
            if kind == "FuncCall":
                names = _names(node["funcname"])
                if not names or (len(names) > 1 and names[:-1] != ["pg_catalog"]):
                    raise SQLPolicyError("Fungsi di luar pg_catalog tidak tersedia dalam ujian.")
                name = names[-1].lower()
                if name in BLOCKED_FUNCTIONS or name.startswith(BLOCKED_FUNCTION_PREFIXES):
                    raise SQLPolicyError(f"Fungsi SQL '{names[-1]}' dilarang dalam ujian.")
            if kind == "RangeVar":
                target = node.get("schemaname")
                if node.get("relname") in {"pg_authid", "pg_shadow"}:
                    raise SQLPolicyError("Katalog kredensial tidak tersedia untuk mahasiswa.")
                if node.get("catalogname"):
                    raise SQLPolicyError("Referensi lintas database tidak diizinkan.")
                if sandbox and target and schema and target != schema:
                    raise SQLPolicyError("Objek berada di luar sandbox Anda.")
                if not sandbox and target and (target.startswith("sandbox_") or target.startswith("_ref_")):
                    raise SQLPolicyError("Sandbox pribadi tidak tersedia melalui database master.")
            if kind == "TypeName":
                names = _names(node.get("names"))
                if not names or names[-1] not in SAFE_TYPES or (len(names) > 1 and names[:-1] != ["pg_catalog"]):
                    raise SQLPolicyError("Tipe data tersebut tidak diizinkan dalam ujian.")
            if kind == "A_Expr":
                names = _names(node.get("name"))
                if len(names) > 1 and names[:-1] != ["pg_catalog"]:
                    raise SQLPolicyError("Operator di luar pg_catalog tidak diizinkan.")
            if kind == "DropStmt":
                if node["removeType"]["name"] not in {"OBJECT_TABLE", "OBJECT_INDEX"}:
                    raise SQLPolicyError("Hanya DROP TABLE atau DROP INDEX yang diizinkan.")
                for obj in node["objects"]:
                    names = _names(obj)
                    if len(names) > 2 or (len(names) == 2 and schema and names[0] != schema):
                        raise SQLPolicyError("Objek berada di luar sandbox Anda.")
                if node.get("concurrent"):
                    raise SQLPolicyError("Operasi concurrent tidak tersedia di sandbox.")
            if kind == "CreateTableAsStmt" and node["objtype"]["name"] != "OBJECT_TABLE":
                raise SQLPolicyError("Materialized view tidak tersedia di sandbox.")
            if kind == "AlterTableCmd" and node["subtype"]["name"] not in ALTER_COMMANDS:
                raise SQLPolicyError("Jenis ALTER TABLE tersebut tidak diizinkan.")
            if kind == "CreateStmt" and (node.get("inhRelations") or node.get("partspec") or node.get("partbound") or node.get("tablespacename")):
                raise SQLPolicyError("Inheritance, partisi, dan tablespace tidak tersedia di sandbox.")
            if kind == "IndexStmt" and (node.get("tableSpace") or node.get("concurrent")):
                raise SQLPolicyError("Tablespace dan indeks concurrent tidak tersedia di sandbox.")
        result.append(ExamStatement(part, tree["@"]))
    return result
