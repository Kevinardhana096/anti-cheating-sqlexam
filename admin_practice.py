"""Admin simulations use the student handlers and a separate SQLite score store."""
from contextlib import closing, contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import database as db
import grading_queue
import admin_security

_initialization_lock = threading.Lock()


@contextmanager
def isolated_store(path):
    token = db.SQLITE_REQUEST_PATH.set(str(path) if path is not None else None)
    try:
        yield
    finally:
        db.SQLITE_REQUEST_PATH.reset(token)


def location(actor):
    primary = Path(os.environ.get('EXAM_SQLITE_PATH', db.SQLITE_DB_PATH)).resolve()
    return primary.parent / 'admin_practice' / (hashlib.sha256((str(primary)+actor['id']).encode()).hexdigest()+'.db')


def snapshot(connection=None):
    with (closing(db.get_sqlite_conn()) if connection is None else nullcontext(connection)) as conn:
        if connection is None:
            conn.execute('BEGIN')
        questions=[dict(r) for r in conn.execute('SELECT * FROM questions ORDER BY id')]
        packages=[dict(r) for r in conn.execute('SELECT * FROM exam_packages ORDER BY code')]
        settings=dict(conn.execute("SELECT key,value FROM system_settings WHERE key IN ('dataset_revision','grading_maintenance')"))
    if settings.get('grading_maintenance'):
        raise db.StudentAccessError('Dataset sedang dipelihara.',503,'dataset_busy')
    semantic=[{k:v for k,v in q.items() if k!='reference_validation'} for q in questions]
    settings={'dataset_revision':settings.get('dataset_revision','1')}
    signature=hashlib.sha256(json.dumps([semantic,packages,settings],sort_keys=True,default=str).encode()).hexdigest()
    return questions,packages,settings,signature


@contextmanager
def commit_guard(actor,manifest):
    with isolated_store(None):
        primary=db.get_sqlite_conn()
    with closing(primary),primary:
        try:
            primary.execute('BEGIN IMMEDIATE')
        except db.sqlite3.OperationalError as error:
            raise db.StudentAccessError('Server sibuk. Coba kembali setelah beberapa saat.',503,'practice_busy') from error
        if snapshot(primary)[3]!=manifest:
            raise db.StudentAccessError('Soal/paket/dataset berubah. Buka ulang IDE pengujian.',409,'practice_changed')
        session=primary.execute('SELECT * FROM admin_sessions WHERE id=?',(actor['id'],)).fetchone()
        now=int(time.time())
        if not session or session['expires_at']<=now or session['last_seen']<=now-admin_security.IDLE_SECONDS:
            raise db.StudentAccessError('Sesi admin berakhir.',403,'practice_expired')
        yield


@contextmanager
def guarded(actor,manifest):
    value=db.SQLITE_COMMIT_GUARD.set(lambda:commit_guard(actor,manifest))
    try:
        yield
    finally:
        db.SQLITE_COMMIT_GUARD.reset(value)


def prepare(actor, token, ip):
    """Refresh the question snapshot on opening the page; never copy student records."""
    questions,packages,settings,signature = snapshot()
    path = location(actor)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    nim = 'ADMIN-PRACTICE-'+hashlib.sha256(str(path).encode()).hexdigest()[:32]
    with _initialization_lock, isolated_store(path):
        db.init_system_db()
        with closing(db.get_sqlite_conn()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute("SELECT value FROM system_settings WHERE key='practice_manifest'").fetchone()
            if not previous or previous[0] != signature:
                conn.execute('DELETE FROM users')
                conn.execute('DELETE FROM questions')
                conn.execute('DELETE FROM exam_packages')
                for table,rows in (('exam_packages',packages),('questions',questions)):
                    for row in rows:
                        names=list(row)
                        conn.execute(f'INSERT INTO {table} ({",".join(names)}) VALUES ({",".join("?" for _ in names)})', list(row.values()))
                conn.execute("INSERT INTO system_settings(key,value) VALUES('practice_manifest',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(signature,))
            for key,value in (('exam_state','active'),('dataset_revision',settings.get('dataset_revision','1'))):
                conn.execute('INSERT INTO system_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        practice_token=hashlib.sha256(('practice:'+token).encode()).hexdigest()
        ok,user,reason=db.login_student(nim,'Simulasi Admin',ip,practice_token,device_id=nim,resume_token=practice_token)
        if not ok:
            raise db.StudentAccessError(reason,409,'practice_session')
        db.mark_student_in_exam(nim,practice_token,ip)
        return db.require_student_access(nim,practice_token,ip),path


def invoke(actor, request, handler, payload=None, query=None):
    path=location(actor)
    if not path.is_file():
        raise db.StudentAccessError('Buka IDE pengujian admin terlebih dahulu.',409,'practice_missing')
    manifest=snapshot()[3]
    with isolated_store(path),guarded(actor,manifest):
        with closing(db.get_sqlite_conn()) as conn:
            saved=conn.execute("SELECT value FROM system_settings WHERE key='practice_manifest'").fetchone()
            user=conn.execute('SELECT * FROM users LIMIT 1').fetchone()
        if not user or not saved or saved[0]!=manifest:
            raise db.StudentAccessError('Soal/paket/dataset berubah. Buka ulang IDE pengujian.',409,'practice_changed')
        request.state.practice_user=dict(user)
        if payload is not None:
            return handler(payload,request)
        return handler(request,**(query or {}))



class Worker(grading_queue.Worker):
    """Drain accepted practice attempts without adding them to the exam queue."""
    def run_once(self):
        now=int(time.time())
        with closing(db.get_sqlite_conn()) as conn:
            if grading_queue.setting(conn,'grading_maintenance',''):
                return False
            revision=grading_queue.setting(conn,'dataset_revision','1')
            actors=[dict(r) for r in conn.execute('SELECT id FROM admin_sessions WHERE expires_at>? AND last_seen>?',
                (now,now-admin_security.IDLE_SECONDS))]
        manifest=snapshot()[3]
        worked=False
        for actor in actors:
            if self.stop_event.is_set():
                break
            path=location(actor)
            if not path.is_file():
                continue
            with isolated_store(path),guarded(actor,manifest):
                with closing(db.get_sqlite_conn()) as conn:
                    if grading_queue.setting(conn,'practice_manifest','')!=manifest:
                        continue
                worked=super().run_once() or worked
        return worked
