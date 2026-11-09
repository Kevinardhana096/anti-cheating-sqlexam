"""Shared master credential and independent, persistent administrator sessions."""
from contextlib import closing
import hashlib
import hmac
import secrets
import time
import uuid

SESSION_SECONDS = 8 * 60 * 60
IDLE_SECONDS = 60 * 60
PREFIX = 'scrypt-v1$'


def hash_key(key):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(key.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()
    return PREFIX + salt + '$' + digest


def check_key(key, encoded):
    if not encoded or not encoded.startswith(PREFIX):
        return False
    try:
        salt, expected = encoded[len(PREFIX):].split('$')
        actual = hashlib.scrypt(key.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def initialize_secret(conn, environment_key=None):
    row = conn.execute("SELECT value FROM system_settings WHERE key='admin_master_key'").fetchone()
    # Environment is a first-install bootstrap, not a password reset on every restart.
    if not row:
        encoded = hash_key((environment_key or '').strip() or 'admin123')
    elif not row[0].startswith(PREFIX):
        encoded = hash_key(row[0])
    else:
        return
    conn.execute("INSERT INTO system_settings(key,value) VALUES('admin_master_key',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encoded,))


def fingerprint(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token):
    return hmac.new(token.encode(), b'sqlexam-admin-csrf-v1', hashlib.sha256).hexdigest()


def _create(conn, ip, previous_token=None):
    now = int(time.time())
    conn.execute('DELETE FROM admin_sessions WHERE expires_at<=? OR last_seen<=?', (now, now-IDLE_SECONDS))
    if previous_token:
        conn.execute('DELETE FROM admin_sessions WHERE token_hash=?', (fingerprint(previous_token),))
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO admin_sessions(id,token_hash,created_at,expires_at,last_seen,login_ip) VALUES(?,?,?,?,?,?)',
                 (uuid.uuid4().hex, fingerprint(token), now, now+SESSION_SECONDS, now, ip))
    return token


def create_session(ip, previous_token=None):
    import database as db
    with closing(db.get_sqlite_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        return _create(conn, ip, previous_token)


def login(key, ip, previous_token=None):
    import database as db
    encoded = db.get_admin_master_key()
    if len(key) > 1024 or not check_key(key, encoded):
        return None
    with closing(db.get_sqlite_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        current = conn.execute("SELECT value FROM system_settings WHERE key='admin_master_key'").fetchone()
        if not current or current[0] != encoded:
            return None
        return _create(conn, ip, previous_token)


def get_session(token):
    import database as db
    if not token or len(token) > 128:
        return None
    now = int(time.time())
    with closing(db.get_sqlite_conn()) as conn, conn:
        row = conn.execute('SELECT * FROM admin_sessions WHERE token_hash=? AND expires_at>? AND last_seen>?',
                           (fingerprint(token), now, now-IDLE_SECONDS)).fetchone()
        if not row:
            return None
        if now-row["last_seen"] >= 30:
            conn.execute('UPDATE admin_sessions SET last_seen=? WHERE id=?', (now, row['id']))
        return dict(row)


def logout(token):
    import database as db
    with closing(db.get_sqlite_conn()) as conn, conn:
        conn.execute('DELETE FROM admin_sessions WHERE token_hash=?', (fingerprint(token),))


def change_key(old_key, new_key, token, ip):
    import database as db
    encoded = db.get_admin_master_key()
    if not check_key(old_key, encoded):
        return None
    replacement = hash_key(new_key)
    with closing(db.get_sqlite_conn()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT value FROM system_settings WHERE key='admin_master_key'").fetchone()
        session = conn.execute('SELECT id FROM admin_sessions WHERE token_hash=? AND expires_at>? AND last_seen>?',
                               (fingerprint(token), int(time.time()), int(time.time())-IDLE_SECONDS)).fetchone()
        if not row or row[0] != encoded or not session:
            return None
        conn.execute("UPDATE system_settings SET value=? WHERE key='admin_master_key'", (replacement,))
        conn.execute('DELETE FROM admin_sessions')
        return _create(conn, ip)


def audit(session_id, method, path, status, ip):
    import database as db
    with closing(db.get_sqlite_conn()) as conn, conn:
        conn.execute('INSERT INTO admin_audit(session_id,method,path,status_code,ip_address) VALUES(?,?,?,?,?)',
                     (session_id, method, path, status, ip))
