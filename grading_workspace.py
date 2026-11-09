"""Disposable restricted sessions and safe copies of a student's workspace."""

from contextlib import closing
import time
import uuid

import psycopg2
from psycopg2 import sql, extras
from pglast import parse_sql
from pglast.stream import RawStream
from pglast.visitors import Visitor

import sandbox_roles
from grading_results import GradingLimitError, MAX_GRADE_BYTES, MAX_GRADE_ROWS, row_key
from sql_policy import prepare_sql
from grading_values import install as install_grading_values


class Rebind(Visitor):
    def __init__(self, source, target):
        super().__init__()
        self.source, self.target = source, target

    def visit_RangeVar(self, ancestors, node):
        if node.schemaname == self.source:
            node.schemaname = self.target

    def visit_ColumnRef(self, ancestors, node):
        if len(node.fields or ()) >= 3 and getattr(node.fields[0], 'sval', None) == self.source:
            node.fields[0].sval = self.target

    def visit_DropStmt(self, ancestors, node):
        for obj in node.objects or ():
            if len(obj) == 2 and obj[0].sval == self.source:
                obj[0].sval = self.target

    def visit_TypeCast(self, ancestors, node):
        names = [item.sval for item in node.typeName.names or ()]
        if names and names[-1] == "regclass" and getattr(getattr(node.arg, "val", None), "sval", "").startswith(self.source + "."):
            node.arg.val.sval = self.target + node.arg.val.sval[len(self.source):]


def rebind(query, source, target):
    tree = parse_sql(query)
    Rebind(source, target)(tree)
    return RawStream()(tree)


def expression_key(expression, schema, constraint=False):
    if not expression:
        return None
    wrapper = "ALTER TABLE placeholder ADD " if constraint else "SELECT "
    return rebind(wrapper + expression, schema, "workspace")


def signature(conn, schema):
    with conn.cursor() as cursor:
        cursor.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind='r'", (schema,))
        tables = {row[0]: {"columns": [], "constraints": [], "sequences": [], "indexes": []} for row in cursor.fetchall()}
        cursor.execute("""SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
            a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname=%s AND c.relkind='r' ORDER BY c.relname,a.attnum""", (schema,))
        for table, name, typ, required, identity, generated, default in cursor.fetchall():
            tables[table]["columns"].append(
                (name, typ, required, identity, generated, expression_key(default, schema)))
        cursor.execute("""SELECT c.relname,pg_get_constraintdef(k.oid),k.convalidated
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND k.contype IN ('p','u','f','c')""", (schema,))
        for table, definition, validated in cursor.fetchall():
            tables[table]["constraints"].append((expression_key(definition, schema, True), validated))
        for table in tables.values():
            table["constraints"].sort()
        cursor.execute("""SELECT t.relname,a.attname,s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle
            FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_depend d ON d.objid=c.oid AND d.classid='pg_class'::regclass AND d.deptype IN ('a','i')
            JOIN pg_class t ON t.oid=d.refobjid JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
            WHERE n.nspname=%s ORDER BY t.relname,a.attname""", (schema,))
        for table, *definition in cursor.fetchall():
            tables[table]["sequences"].append(tuple(definition))
        cursor.execute("""SELECT t.relname,i.indisunique,am.amname,
            ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true) FROM generate_series(1,i.indnatts) k),
            pg_get_expr(i.indpred,i.indrelid),i.indnkeyatts,
            COALESCE((to_jsonb(i)->>'indnullsnotdistinct')::boolean,false)
            FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_class x ON x.oid=i.indexrelid JOIN pg_am am ON am.oid=x.relam
            WHERE n.nspname=%s AND NOT EXISTS(SELECT 1 FROM pg_constraint k WHERE k.conindid=i.indexrelid)""", (schema,))
        for table, unique, method, columns, predicate,key_count,nulls_not_distinct in cursor.fetchall():
            tables[table]["indexes"].append((unique, method, tuple(columns[:key_count]),tuple(columns[key_count:]),
                nulls_not_distinct,expression_key(predicate, schema)))
        for table in tables.values():
            table["indexes"].sort(key=repr)
        return tables


class Workspace:
    def __init__(self, deadline):
        import database as db
        self.nim = "_evaluation_" + uuid.uuid4().hex
        self.schema = None
        self.conn = None
        self.deadline = deadline
        self.virtual = None
        try:
            self.schema = db.init_student_sandbox_schema(self.nim)
            _, role, password = sandbox_roles.credentials(self.nim)
            self.conn = psycopg2.connect(dbname=db.DEFAULT_EXAM_DB, user=role, password=password,
                                        host=db.PG_HOST, port=db.PG_PORT, connect_timeout=5)
            self.conn.set_session(autocommit=False)
            with self.conn.cursor() as cursor:
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema)))
                cursor.execute("SET LOCAL lock_timeout=3000")
        except Exception:
            self.close()
            raise

    def check(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise GradingLimitError("Waktu evaluasi habis; jawaban memerlukan pemeriksaan pengawas.")
        return max(1, int(remaining * 1000))

    def execute(self, command, params=None):
        with self.conn.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout=%s", (self.check(),))
            cursor.execute(command, params)
            if cursor.rowcount > 10000:
                raise GradingLimitError("Perubahan data melampaui batas evaluator.")

    def run(self, statements, source_schema=None):
        for statement in statements:
            self.check()
            if statement.kind == "virtual_create":
                self.virtual = statement.virtual_name
            elif statement.kind == "virtual_use":
                if self.virtual != statement.virtual_name:
                    raise ValueError("Database virtual belum dibuat.")
            elif statement.kind == "virtual_drop":
                if self.virtual and self.virtual != statement.virtual_name:
                    raise ValueError("Nama database virtual tidak sesuai.")
                for table in signature(self.conn, self.schema):
                    self.execute(sql.SQL("DROP TABLE {}.{} CASCADE").format(sql.Identifier(self.schema), sql.Identifier(table)))
                self.virtual = None
            elif statement.kind == "SelectStmt":
                with self.cursor(statement.text, source_schema) as cursor:
                    count = size = 0
                    for row in self.rows(cursor):
                        count += 1
                        size += len(row_key(row))
                        if count > MAX_GRADE_ROWS or size > MAX_GRADE_BYTES:
                            raise GradingLimitError("Hasil SQL melampaui batas evaluator.")
            else:
                text = rebind(statement.text, source_schema, self.schema) if source_schema else statement.text
                prepare_sql(text, sandbox=True, schema=self.schema)
                self.execute(text)

    def cursor(self, query, source_schema=None):
        with self.conn.cursor() as control:
            control.execute("SET LOCAL statement_timeout=%s", (self.check(),))
        query = rebind(query, source_schema, self.schema) if source_schema else query
        prepare_sql(query, sandbox=True, schema=self.schema)
        cursor = self.conn.cursor(name="grade_" + uuid.uuid4().hex)
        install_grading_values(cursor)
        cursor.execute(query)
        cursor.fetchmany(0)
        return cursor

    def rows(self, cursor):
        while True:
            with self.conn.cursor() as control:
                control.execute("SET LOCAL statement_timeout=%s", (self.check(),))
            batch = cursor.fetchmany(128)
            if not batch:
                break
            yield from batch

    def close(self):
        import database as db
        if self.conn:
            self.conn.close()
            self.conn = None
        if self.schema:
            if not db.cleanup_student_sandbox_schema(self.nim):
                raise RuntimeError("Cleanup workspace evaluator gagal.")
            self.schema = None


def clone_workspace(nim, targets):
    """Read a consistent source snapshot; reconstructed expressions run only as restricted roles."""
    import database as db
    source = db.get_clean_student_schema_name(nim)
    with closing(db.get_pg_admin_connection()) as conn, conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout=5000")
            cursor.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind='r' ORDER BY c.relname", (source,))
            names = [row[0] for row in cursor.fetchall()]
            if len(names) > 64:
                raise GradingLimitError("Workspace memiliki terlalu banyak tabel untuk penilaian otomatis.")
            cursor.execute("""SELECT c.relname,s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle,
                t.relname,a.attname,a.attidentity
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_sequence s ON s.seqrelid=c.oid
                LEFT JOIN pg_depend d ON d.objid=c.oid AND d.classid='pg_class'::regclass AND d.deptype IN ('a','i')
                LEFT JOIN pg_class t ON t.oid=d.refobjid LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
                WHERE n.nspname=%s""", (source,))
            sequences = cursor.fetchall()
            for seq, start, step, minimum, maximum, cache, cycle, table, column, identity in sequences:
                if identity:
                    continue
                for target in targets:
                    target.execute(sql.SQL("CREATE SEQUENCE {}.{} START %s INCREMENT %s MINVALUE %s MAXVALUE %s CACHE %s {} CYCLE").format(
                        sql.Identifier(target.schema), sql.Identifier(seq), sql.SQL("" if cycle else "NO")),
                        (start, step, minimum, maximum, cache))
            definitions = {}
            for table in names:
                targets[0].check()
                cursor.execute("""SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
                    a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)
                    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                    LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                    WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""", (source, table))
                columns = cursor.fetchall()
                definitions[table] = columns
                for target in targets:
                    parts = []
                    for name, typ, required, identity, generated, default in columns:
                        item = sql.Identifier(name).as_string(conn) + " " + typ
                        if identity:
                            seq = next(row for row in sequences if row[8] == name and row[7] == table)
                            _, start, step, minimum, maximum, cache, cycle, *_ = seq
                            item += " GENERATED " + ("ALWAYS" if identity == "a" else "BY DEFAULT") + " AS IDENTITY"
                            item += f" (START WITH {start} INCREMENT BY {step} MINVALUE {minimum} MAXVALUE {maximum} CACHE {cache} {'CYCLE' if cycle else 'NO CYCLE'})"
                        elif generated:
                            expression = rebind("SELECT " + default, source, target.schema)[7:]
                            item += " GENERATED ALWAYS AS (" + expression + ") STORED"
                        elif default:
                            expression = rebind("SELECT " + default, source, target.schema)[7:]
                            item += " DEFAULT " + expression
                        if required:
                            item += " NOT NULL"
                        parts.append(item)
                    command = sql.SQL("CREATE TABLE {}.{} ({})").format(sql.Identifier(target.schema), sql.Identifier(table), sql.SQL(",".join(parts))).as_string(conn)
                    prepare_sql(command, sandbox=True, schema=target.schema)
                    target.execute(command)
            total_rows = total_bytes = 0
            for table, columns in definitions.items():
                writable = [item[0] for item in columns if not item[4]]
                fields = sql.SQL(",").join(map(sql.Identifier, writable))
                with conn.cursor(name="clone_" + uuid.uuid4().hex) as data:
                    text_fields=sql.SQL(',').join(sql.SQL('{}::text').format(sql.Identifier(name)) for name in writable)
                    data.execute(sql.SQL("SELECT {} FROM {}.{}").format(text_fields, sql.Identifier(source), sql.Identifier(table)))
                    while True:
                        targets[0].check()
                        batch = data.fetchmany(128)
                        if not batch:
                            break
                        total_rows += len(batch)
                        total_bytes += sum(len(row_key(row)) for row in batch)
                        if total_rows > MAX_GRADE_ROWS or total_bytes > MAX_GRADE_BYTES:
                            raise GradingLimitError("Snapshot workspace melampaui batas evaluator.")
                        for target in targets:
                            command = sql.SQL("INSERT INTO {}.{} ({}) OVERRIDING SYSTEM VALUE VALUES %s").format(sql.Identifier(target.schema), sql.Identifier(table), fields).as_string(conn)
                            with target.conn.cursor() as output:
                                output.execute("SET LOCAL statement_timeout=%s", (target.check(),))
                                types=[item[1] for item in columns if not item[4]]
                                template='('+','.join('%s::'+typ for typ in types)+')'
                                extras.execute_values(output, command, batch,template=template, page_size=128)
            constraints = []
            for table in names:
                cursor.execute("""SELECT pg_get_constraintdef(k.oid),k.contype FROM pg_constraint k
                    JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname=%s AND c.relname=%s AND k.contype IN ('p','u','c','f') ORDER BY k.contype='f'""", (source, table))
                constraints.extend((kind == "f", table, definition) for definition, kind in cursor.fetchall())
            for _, table, definition in sorted(constraints):
                for target in targets:
                    command = sql.SQL("ALTER TABLE {}.{} ADD ").format(sql.Identifier(source), sql.Identifier(table)).as_string(conn) + definition
                    command = rebind(command, source, target.schema)
                    prepare_sql(command, sandbox=True, schema=target.schema)
                    target.execute(command)
            cursor.execute("""SELECT pg_get_indexdef(i.indexrelid) FROM pg_index i
                JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=%s AND NOT EXISTS(SELECT 1 FROM pg_constraint k WHERE k.conindid=i.indexrelid)""", (source,))
            for definition, in cursor.fetchall():
                for target in targets:
                    command = rebind(definition, source, target.schema)
                    prepare_sql(command, sandbox=True, schema=target.schema)
                    target.execute(command)
            for seq, _, _, _, _, _, _, table, column, identity in sequences:
                cursor.execute(sql.SQL("SELECT last_value,is_called FROM {}.{}").format(sql.Identifier(source), sql.Identifier(seq)))
                value, called = cursor.fetchone()
                for target in targets:
                    with target.conn.cursor() as output:
                        if identity:
                            output.execute("SELECT pg_get_serial_sequence(%s,%s)", (target.schema + "." + table, column))
                            destination = output.fetchone()[0]
                        else:
                            destination = target.schema + "." + seq
                            if table and column:
                                output.execute(sql.SQL("ALTER SEQUENCE {}.{} OWNED BY {}.{}.{}").format(sql.Identifier(target.schema), sql.Identifier(seq), sql.Identifier(target.schema), sql.Identifier(table), sql.Identifier(column)))
                        output.execute("SELECT setval(%s::regclass,%s,%s)", (destination, value, called))
    return source
