"""Offline backup bundles and recovery into new destinations only."""
from contextlib import closing
from dataclasses import dataclass, field
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import time
import uuid

FORMAT_VERSION = 1


@dataclass
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str = field(default='', repr=False)
    binaries: str = ''

    def tool(self, name):
        executable = name + ('.exe' if os.name == 'nt' else '')
        path = str(Path(self.binaries)/executable) if self.binaries else shutil.which(executable)
        if not path or not Path(path).is_file():
            raise ValueError(f'{name} tidak ditemukan. Berikan direktori --pg-bin.')
        return path

    def environment(self):
        env = os.environ.copy()
        env.update(PGHOST=self.host, PGPORT=str(self.port), PGUSER=self.user,
                   PGPASSWORD=self.password, PGCONNECT_TIMEOUT='5')
        # Ignore ambient libpq service/connection options during a recovery operation.
        for name in ('PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGDATABASE'):
            env.pop(name, None)
        return env


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def sqlite_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)


def check_sqlite(path):
    with closing(sqlite_readonly(path)) as conn:
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Integritas SQLite tidak valid.')
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Relasi SQLite tidak valid.')
        required = {'users','questions','submissions','submission_attempts','admin_sessions','admin_audit','system_settings'}
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            raise ValueError('Backup memerlukan skema aplikasi fase 5 atau lebih baru.')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version not in (4,5):
            raise ValueError('Versi skema SQLite tidak didukung oleh format backup ini.')
        if version == 5 and not {"grading_jobs","grading_decisions"} <= tables:
            raise ValueError('Tabel antrean/keputusan penilaian tidak lengkap.')
        return version


def pg_command(config, command):
    result = subprocess.run(command, env=config.environment(), capture_output=True, timeout=300,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if result.returncode:
        # Do not echo libpq errors, connection strings, or dump content into application logs.
        raise RuntimeError(f'{Path(command[0]).stem} gagal (exit {result.returncode}). Periksa tujuan dan versi PostgreSQL.')


def create_backup(sqlite_path, destination, *, uploads=None, postgres=None, databases=()):
    started = time.perf_counter()
    source = Path(sqlite_path).resolve()
    target = Path(destination).resolve()
    if not source.is_file() or target.exists():
        raise ValueError('Sumber SQLite harus ada dan direktori backup harus baru.')
    upload_root = Path(uploads).resolve() if uploads else None
    if upload_root and (target == upload_root or upload_root in target.parents):
        raise ValueError('Direktori backup tidak boleh berada dalam direktori upload.')
    if databases and postgres is None:
        raise ValueError('Konfigurasi PostgreSQL diperlukan.')
    if any(name not in {'pagila','classicmodels'} for name in databases) or len(set(databases)) != len(databases):
        raise ValueError('Nama database backup tidak valid.')
    # Publish only after every file has been written and hashed. Failed work stays .incomplete.
    staging = target.with_name(target.name+'.incomplete-'+uuid.uuid4().hex)
    staging.mkdir(parents=True, mode=0o700)
    with closing(sqlite_readonly(source)) as live, closing(sqlite3.connect(staging/'exam_system.db')) as copy:
        live.backup(copy, pages=128, sleep=.01)
        copy.execute("PRAGMA journal_mode=DELETE")
    schema_version = check_sqlite(staging/'exam_system.db')
    if upload_root and upload_root.exists():
        for path in upload_root.rglob('*'):
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('Upload berupa symlink/junction tidak boleh dibackup.')
            if path.is_file():
                relative = path.relative_to(upload_root)
                output = staging/'static/uploads/questions'/relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, output)
    for name in databases:
        output = staging/(name+'.dump')
        pg_command(postgres, [postgres.tool('pg_dump'),'--format=custom','--no-owner','--no-privileges',
                              '--file',str(output),'--dbname',name])
    files = {path.relative_to(staging).as_posix(): {'sha256':digest(path),'bytes':path.stat().st_size}
             for path in sorted(staging.rglob('*')) if path.is_file()}
    manifest = {'format_version':FORMAT_VERSION,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'sqlite_version':schema_version,'databases':list(databases),'files':files,
                'consistency':'offline; operator must stop application and other writers',
                'includes_secrets':True,'postgres_roles_included':False,
                'elapsed_seconds':round(time.perf_counter()-started,3)}
    (staging/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    staging.rename(target)
    return manifest


def verify_backup(directory):
    root = Path(directory).resolve()
    if not root.is_dir() or (root/'manifest.json').is_symlink():
        raise ValueError('Direktori/manifest backup tidak valid.')
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format_version') != FORMAT_VERSION:
        raise ValueError('Versi format backup tidak didukung.')
    files = manifest.get('files',{})
    if 'exam_system.db' not in files or any(name not in {'pagila','classicmodels'} for name in manifest.get('databases',[])):
        raise ValueError('Manifest backup tidak lengkap.')
    expected = {'exam_system.db',*(name+'.dump' for name in manifest.get('databases',[]))}
    for name, record in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Path manifest tidak aman.')
        if name not in expected and not name.startswith('static/uploads/questions/'):
            raise ValueError('Berkas manifest tidak diizinkan.')
        path = root.joinpath(*relative.parts)
        if root not in path.resolve().parents or any(part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()) for part in (path,*path.parents) if part != root):
            raise ValueError('Path backup keluar dari direktori sumber.')
        if not path.is_file() or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise ValueError(f'Checksum/ukuran backup tidak cocok: {name}')
    if not expected <= set(files):
        raise ValueError('Dump PostgreSQL tidak lengkap.')
    if check_sqlite(root/'exam_system.db') != manifest['sqlite_version']:
        raise ValueError('Versi SQLite tidak cocok dengan manifest.')
    return manifest


def restore_backup(directory, destination, *, postgres=None, database_prefix='', sqlite_only=False):
    started = time.perf_counter()
    manifest = verify_backup(directory)
    root, target = Path(directory).resolve(), Path(destination).resolve()
    if target.exists():
        raise ValueError('Tujuan pemulihan harus direktori baru; overwrite tidak diizinkan.')
    if manifest['databases'] and postgres is None and not sqlite_only:
        raise ValueError('Pemulihan lengkap memerlukan PostgreSQL; SQLite-only harus dipilih eksplisit.')
    if postgres and not manifest['databases']:
        raise ValueError('Backup ini tidak memuat PostgreSQL.')
    if database_prefix and (not database_prefix.replace('_','').isalnum() or len(database_prefix)>25):
        raise ValueError('Prefix database tidak valid.')
    mapping = {name:database_prefix+name for name in manifest['databases']} if postgres else {}
    # Preflight all names before creating either database. Existing databases are never dropped.
    if postgres:
        import psycopg2
        from psycopg2 import sql
        with closing(psycopg2.connect(dbname='postgres', host=postgres.host,port=postgres.port,
                                     user=postgres.user,password=postgres.password,connect_timeout=5)) as control:
            control.autocommit = True
            with control.cursor() as cursor:
                cursor.execute('SELECT datname FROM pg_database WHERE datname=ANY(%s)', (list(mapping.values()),))
                if cursor.fetchone():
                    raise ValueError('Database tujuan sudah ada. Gunakan cluster kosong atau prefix baru.')
                for source, name in mapping.items():
                    cursor.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0 ENCODING \'UTF8\'').format(sql.Identifier(name)))
                    pg_command(postgres,[postgres.tool('pg_restore'),'--exit-on-error','--single-transaction',
                                         '--no-owner','--no-privileges','--dbname',name,str(root/(source+'.dump'))])
    target.mkdir(parents=True, mode=0o700)
    for name in manifest['files']:
        if name.endswith('.dump'):
            continue
        output = target/name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name,output)
    # Never reactivate student/admin sessions copied from a previous server.
    with closing(sqlite3.connect(target/'exam_system.db')) as conn, conn:
        conn.execute('DELETE FROM admin_sessions')
        if manifest['sqlite_version'] == 5:
            conn.execute("UPDATE grading_jobs SET status='stale',lease_token=NULL,lease_until=NULL,version=version+1,feedback='Pemulihan backup; pengawas harus meminta regrade baru.' WHERE status IN ('queued','running')")
            conn.execute("DELETE FROM system_settings WHERE key='grading_maintenance'")
        conn.execute("UPDATE users SET session_token=NULL,status='offline'")
        conn.execute("INSERT INTO system_settings(key,value) VALUES('exam_state','waiting') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        conn.execute("INSERT INTO system_settings(key,value) VALUES('exam_revision','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
        conn.execute("INSERT INTO exam_logs(action_type,details) VALUES('restore_backup','Pemulihan offline; sesi dicabut, ujian menunggu pengawas.')")
    check_sqlite(target/'exam_system.db')
    result = {'postgres_databases':mapping,'sqlite':str(target/'exam_system.db'),
              'sessions_revoked':True,'exam_state':'waiting','postgres_restored':bool(mapping),
              'elapsed_seconds':round(time.perf_counter()-started,3)}
    (target/'recovery.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
