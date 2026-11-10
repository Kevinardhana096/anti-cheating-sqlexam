"""Durable grading retries and append-only decisions, fenced by question/exam/dataset revisions."""
from contextlib import closing, contextmanager
import threading
import time
import uuid

LEASE_SECONDS = 90
MAX_ATTEMPTS = 3


def setting(conn, key, default='0'):
    row = conn.execute('SELECT value FROM system_settings WHERE key=?',(key,)).fetchone()
    return row[0] if row else default


def last_decision(conn, attempt_id):
    return conn.execute('SELECT COALESCE(MAX(id),0) FROM grading_decisions WHERE attempt_id=?',(attempt_id,)).fetchone()[0]


def migrate(conn):
    conn.execute('''CREATE TABLE grading_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id INTEGER NOT NULL REFERENCES submission_attempts(id) ON DELETE CASCADE,
        question_revision INTEGER NOT NULL, exam_revision INTEGER NOT NULL, dataset_revision INTEGER NOT NULL, student_revision INTEGER NOT NULL DEFAULT 0,
        active_database TEXT NOT NULL, status TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
        run_after REAL NOT NULL DEFAULT 0, lease_token TEXT, lease_until REAL,
        decision_base INTEGER NOT NULL DEFAULT 0, requested_by TEXT, last_status TEXT NOT NULL DEFAULT '',
        feedback TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(attempt_id,question_revision))''')
    conn.execute('CREATE INDEX idx_grading_jobs_due ON grading_jobs(status,run_after,lease_until,id)')
    conn.execute('''CREATE TABLE grading_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id INTEGER NOT NULL REFERENCES submission_attempts(id) ON DELETE CASCADE,
        question_revision INTEGER NOT NULL, graded INTEGER NOT NULL, is_correct INTEGER, score INTEGER,
        eval_status TEXT NOT NULL, feedback TEXT NOT NULL, source TEXT NOT NULL, admin_session_id TEXT,
        run_token TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('CREATE INDEX idx_grading_decisions_attempt ON grading_decisions(attempt_id,question_revision,id)')
    # Old pending answers have no captured replay context; migration must not guess it.
    conn.execute('''INSERT INTO grading_jobs(attempt_id,question_revision,exam_revision,dataset_revision,active_database,status,feedback)
        SELECT a.id,a.question_revision,0,0,COALESCE(q.target_database,'pagila'),'review','Migrasi: pengawas perlu memeriksa konteks jawaban.'
        FROM submission_attempts a JOIN questions q ON q.id=a.question_id WHERE a.graded=0''')


def replayable(question, submitted_query=""):
    from grading_results import policy_from
    try:
        if policy_from(question['grading_policy']).mode != 'automatic' or not question['expected_query']:
            return False
        from pglast import parse_sql
        from sql_policy import _walk, NON_REPLAYABLE_FUNCTIONS
        for text in (question['expected_query'],question['setup_query'],submitted_query):
            for statement in parse_sql(text or ''):
                for node in _walk(statement.stmt()):
                    if node.get('@')=='SQLValueFunction':
                        return False
                    if node.get('@')=='FuncCall':
                        name = node['funcname'][-1]['sval'].lower()
                        if name in NON_REPLAYABLE_FUNCTIONS or (name=='age' and len(node.get('args') or [])<2):
                            return False
        target = (question['target_database'] or '').strip().lower().split('(')[0].strip()
        if target not in {'pagila','classicmodels','sandbox_pribadi'}:
            return False
        return target != 'sandbox_pribadi' or bool(question['setup_query'].strip())
    except Exception:
        return False


def enqueue_pending(conn, attempt, question, active_database=None):
    if attempt['graded']:
        return None
    automatic = attempt['eval_status'] in {'evaluation_limit','evaluation_error'} and replayable(question,attempt['submitted_query'])
    status = 'queued' if automatic else 'review'
    conn.execute('''INSERT INTO grading_jobs(attempt_id,question_revision,exam_revision,dataset_revision,
        active_database,status,last_status,feedback,student_revision) VALUES(?,?,?,?,?,?,?,?,?)''',
        (attempt['id'],question['question_revision'],int(setting(conn,'exam_revision')),
         int(setting(conn,'dataset_revision')),active_database or question['target_database'] or 'pagila',status,
         attempt['eval_status'], 'Menunggu retry otomatis.' if automatic else 'Memerlukan pemeriksaan pengawas; konteks replay tidak dijamin.',
         conn.execute('SELECT grading_revision FROM users WHERE id=?',(attempt['user_id'],)).fetchone()[0]))
    return status


def effective_attempt(conn, row, revision=None):
    result = dict(row)
    if revision is None:
        revision = conn.execute('SELECT question_revision FROM questions WHERE id=?',(row['question_id'],)).fetchone()[0]
    decision = conn.execute('''SELECT * FROM grading_decisions WHERE attempt_id=? AND question_revision=? AND graded=1
        ORDER BY id DESC LIMIT 1''',(row['id'],revision)).fetchone()
    result['decision_id'] = last_decision(conn,row['id'])
    if decision:
        result['initial_result'] = {key:result[key] for key in ('graded','score','is_correct','eval_status','feedback','question_revision')}
        for key in ('graded','score','is_correct','eval_status','feedback','question_revision'):
            result[key] = decision[key]
        result['decision_source'] = decision['source']
    job = conn.execute('SELECT id,status,tries,feedback,version FROM grading_jobs WHERE attempt_id=? AND question_revision=?',
                       (row['id'],revision)).fetchone()
    result['grading_job'] = dict(job) if job else None
    return result


def rebuild_best(conn, user_id, question):
    candidates = []
    for row in conn.execute('SELECT * FROM submission_attempts WHERE user_id=? AND question_id=?',(user_id,question['id'])):
        effective = effective_attempt(conn,row,question['question_revision'])
        if effective['graded'] and effective['question_revision']==question['question_revision']:
            candidates.append(effective)
    if not candidates:
        return
    best = max(candidates,key=lambda a:(a['score'],a['is_correct'],a['id']))
    conn.execute('''INSERT INTO submissions(user_id,question_id,submitted_query,submitted_at,is_correct,score,eval_status,feedback,question_revision)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,question_id) DO UPDATE SET
        submitted_query=excluded.submitted_query,submitted_at=excluded.submitted_at,is_correct=excluded.is_correct,
        score=excluded.score,eval_status=excluded.eval_status,feedback=excluded.feedback,question_revision=excluded.question_revision''',
        (user_id,question['id'],best['submitted_query'],best['submitted_at'],best['is_correct'],best['score'],
         best['eval_status'],best['feedback'],question['question_revision']))


def context(conn, attempt_id):
    import database as db
    row = conn.execute('''SELECT a.*,u.nim,u.selected_category,u.grading_revision FROM submission_attempts a JOIN users u ON u.id=a.user_id
        WHERE a.id=?''',(attempt_id,)).fetchone()
    if not row:
        raise db.StudentAccessError('Percobaan tidak ditemukan.',404,'attempt_missing')
    question = conn.execute('SELECT * FROM questions WHERE id=?',(row['question_id'],)).fetchone()
    if not question or row['selected_category'] != question['category']:
        raise db.StudentAccessError('Paket peserta/soal sudah berubah.',409,'grading_context_changed')
    return dict(row),dict(question)


def stale_reason(conn, job):
    if setting(conn,'grading_maintenance',''):
        return 'Dataset sedang dipelihara.'
    try:
        attempt,question = context(conn,job['attempt_id'])
    except Exception:
        return 'Percobaan atau paket telah berubah.'
    if attempt['grading_revision'] != job['student_revision']:
        return 'Konteks paket peserta direset.'
    if question['question_revision'] != job['question_revision']:
        return 'Revisi soal berubah.'
    revision = int(setting(conn,'exam_revision'))
    allowed_stop = setting(conn,'exam_state','waiting')=='finished' and revision==job['exam_revision']+1
    if revision != job['exam_revision'] and not allowed_stop:
        return 'Siklus ujian berubah.'
    if int(setting(conn,'dataset_revision')) != job['dataset_revision']:
        return 'Dataset berubah.'
    if last_decision(conn,job['attempt_id']) != job['decision_base']:
        return 'Keputusan penilaian lain sudah tersimpan.'
    return None


def claim():
    import database as db
    now = time.time()
    with closing(db.get_sqlite_conn()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if setting(conn,'grading_maintenance',''):
            return None
        row = conn.execute('''SELECT * FROM grading_jobs WHERE (status='queued' AND run_after<=?)
            OR (status='running' AND lease_until<=?) ORDER BY id LIMIT 1''',(now,now)).fetchone()
        if not row:
            return None
        job = dict(row)
        reason = stale_reason(conn,job)
        if reason or job['tries']>=MAX_ATTEMPTS:
            conn.execute("UPDATE grading_jobs SET status=?,feedback=?,lease_token=NULL,lease_until=NULL,version=version+1 WHERE id=?",
                         ('stale' if reason else 'review',reason or 'Batas retry tercapai.',job['id']))
            return {'skipped':True}
        token = uuid.uuid4().hex
        conn.execute("UPDATE grading_jobs SET status='running',tries=tries+1,lease_token=?,lease_until=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (token,now+LEASE_SECONDS,job['id']))
        job.update(lease_token=token,tries=job['tries']+1)
        attempt,question = context(conn,job['attempt_id'])
        return {'job':job,'attempt':attempt,'question':question}


def record_decision(conn, attempt, question, result, source, actor, token):
    graded = bool(result.get('graded',True))
    score = result.get('score') if graded else None
    if graded and (isinstance(score,bool) or not isinstance(score,int) or not 0<=score<=int(question['score_weight'])):
        raise ValueError('Nilai evaluator tidak valid.')
    decision = conn.execute('''INSERT INTO grading_decisions(attempt_id,question_revision,graded,is_correct,score,eval_status,feedback,source,admin_session_id,run_token)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',(attempt['id'],question['question_revision'],int(graded),
        int(bool(result['is_correct'])) if graded else None,score,result['eval_status'],result['feedback'],source,actor,token))
    if graded:
        rebuild_best(conn,attempt['user_id'],question)
    conn.execute("INSERT INTO exam_logs(user_id,action_type,details) VALUES(?,'grading_decision',?)",
                 (attempt['user_id'],f"Percobaan {attempt['id']}, keputusan {decision.lastrowid}, sumber {source}, revisi {question['question_revision']}."))
    return decision.lastrowid


def finish(item, result):
    import database as db
    original = item['job']
    with db.SQLITE_COMMIT_GUARD.get()(), closing(db.get_sqlite_conn()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT * FROM grading_jobs WHERE id=? AND status='running' AND lease_token=?",(original['id'],original['lease_token'])).fetchone()
        if not row:
            return False
        job = dict(row)
        reason = stale_reason(conn,job)
        if reason:
            conn.execute("UPDATE grading_jobs SET status='stale',feedback=?,lease_token=NULL,lease_until=NULL,version=version+1 WHERE id=?",(reason,job['id']))
            return False
        attempt,question = context(conn,job['attempt_id'])
        decision_id = record_decision(conn,attempt,question,result,'auto_retry' if not job['requested_by'] else 'admin_regrade',
                                      job['requested_by'],job['lease_token'])
        graded = result.get('graded',True)
        retry = not graded and result['eval_status'] in {'evaluation_error','evaluation_limit'} and job['tries']<MAX_ATTEMPTS
        state = 'completed' if graded else ('queued' if retry else 'review')
        conn.execute('''UPDATE grading_jobs SET status=?,decision_base=?,last_status=?,feedback=?,run_after=?,lease_token=NULL,
            lease_until=NULL,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (state,decision_id,result['eval_status'],result['feedback'],time.time()+min(2**job['tries'],30),job['id']))
        return True


def manual(attempt_id, revision, expected_decision_id, score, reason, actor):
    import database as db
    with closing(db.get_sqlite_conn()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        attempt,question = context(conn,attempt_id)
        if setting(conn,'grading_maintenance','') or question['question_revision']!=revision or last_decision(conn,attempt_id)!=expected_decision_id:
            raise db.StudentAccessError('Konteks/keputusan berubah. Muat ulang sebelum menilai.',409,'grading_conflict')
        if isinstance(score,bool) or not isinstance(score,int) or not 0<=score<=int(question['score_weight']) or not reason.strip() or len(reason)>2000:
            raise db.StudentAccessError('Nilai atau alasan tidak valid.',422,'invalid_manual_grade')
        result = {'graded':True,'score':score,'is_correct':score==int(question['score_weight']),
                  'eval_status':'manual_graded','feedback':reason.strip()}
        decision = record_decision(conn,attempt,question,result,'manual',actor,uuid.uuid4().hex)
        conn.execute("UPDATE grading_jobs SET status='cancelled',lease_token=NULL,lease_until=NULL,version=version+1,feedback='Diselesaikan melalui penilaian manual.' WHERE attempt_id=? AND status IN ('running','queued','review')",(attempt_id,))
        return decision


def regrade(attempt_id, revision, expected_decision_id, actor):
    import database as db
    with closing(db.get_sqlite_conn()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        attempt,question = context(conn,attempt_id)
        if setting(conn,'grading_maintenance','') or question['question_revision']!=revision or last_decision(conn,attempt_id)!=expected_decision_id:
            raise db.StudentAccessError('Konteks/keputusan berubah. Muat ulang sebelum regrade.',409,'grading_conflict')
        if not replayable(question,attempt['submitted_query']):
            raise db.StudentAccessError('Replay otomatis memerlukan acuan otomatis dan setup sandbox eksplisit.',409,'replay_not_safe')
        existing = conn.execute('SELECT status FROM grading_jobs WHERE attempt_id=? AND question_revision=?',(attempt_id,revision)).fetchone()
        if existing and existing[0] in {'queued','running'}:
            raise db.StudentAccessError('Pekerjaan sudah mengantre/berjalan.',409,'already_queued')
        conn.execute('''INSERT INTO grading_jobs(attempt_id,question_revision,exam_revision,dataset_revision,active_database,status,requested_by,decision_base,student_revision)
            VALUES(?,?,?,?,?,'queued',?,?,?) ON CONFLICT(attempt_id,question_revision) DO UPDATE SET
            status='queued',tries=0,run_after=0,lease_token=NULL,lease_until=NULL,requested_by=excluded.requested_by,
            decision_base=excluded.decision_base,exam_revision=excluded.exam_revision,dataset_revision=excluded.dataset_revision,student_revision=excluded.student_revision,
            version=version+1,updated_at=CURRENT_TIMESTAMP''',
            (attempt_id,revision,int(setting(conn,'exam_revision')),int(setting(conn,'dataset_revision')),question['target_database'],actor,expected_decision_id,attempt['grading_revision']))
        return conn.execute('SELECT id FROM grading_jobs WHERE attempt_id=? AND question_revision=?',(attempt_id,revision)).fetchone()[0]


@contextmanager
def dataset_maintenance():
    import database as db
    token = uuid.uuid4().hex
    with closing(db.get_sqlite_conn()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        if setting(conn,'exam_state','waiting')=='active' or setting(conn,'grading_maintenance',''):
            raise db.StudentAccessError('Akhiri ujian dan selesaikan maintenance lain sebelum mengganti dataset.',409,'dataset_busy')
        conn.execute("INSERT INTO system_settings(key,value) VALUES('grading_maintenance',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(token,))
        conn.execute("INSERT INTO system_settings(key,value) VALUES('dataset_revision','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
        conn.execute("UPDATE grading_jobs SET status='stale',lease_token=NULL,lease_until=NULL,version=version+1,feedback='Dataset diganti.' WHERE status IN ('queued','running')")
    try:
        yield
    finally:
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute("DELETE FROM system_settings WHERE key='grading_maintenance' AND value=?",(token,))


class Worker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.last_error = None

    def run_once(self):
        item = claim()
        if item is None:
            return False
        if item.get('skipped'):
            return True
        import database as db
        q,a = item['question'],item['attempt']
        try:
            result = db.evaluate_sql_submission(a['submitted_query'],q['expected_query'],int(q['score_weight']),
                q['target_database'],item['job']['active_database'],a['nim'],q['grading_policy'],q['setup_query'],q['id'])
        except Exception:
            from grading_engine import outcome
            result = outcome('evaluation_error',graded=False)
        finish(item,result)
        return True

    def loop(self):
        while not self.stop_event.is_set():
            try:
                worked = self.run_once()
                self.last_error = None
            except Exception as error:
                worked = False
                self.last_error = type(error).__name__
            if not worked:
                self.stop_event.wait(.5)

    def start(self):
        self.thread = threading.Thread(target=self.loop,name='grading-queue',daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=60)
            if self.thread.is_alive():
                raise RuntimeError('Worker penilaian belum berhenti; pool tidak boleh ditutup.')
