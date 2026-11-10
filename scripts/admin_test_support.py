"""Authenticate fixture clients without a process-wide admin backdoor."""
import admin_security


def authenticate_admin(client):
    token = admin_security.create_session('testclient')
    client.cookies.set('admin_session', token)
    client.headers['X-CSRF-Token'] = admin_security.csrf_token(token)
    return token
