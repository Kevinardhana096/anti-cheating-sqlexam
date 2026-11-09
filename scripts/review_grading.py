"""Authenticated administrator CLI for queue inspection, manual grades, and regrading."""
import argparse
import getpass
import json
import sys
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    commands = parser.add_subparsers(dest='command',required=True)
    listing = commands.add_parser('list')
    listing.add_argument('--status',choices=['queued','running','review','completed','stale','cancelled'])
    listing.add_argument('--before-id',type=int)
    detail = commands.add_parser('show')
    detail.add_argument('attempt_id',type=int)
    for name in ('manual','regrade'):
        command = commands.add_parser(name)
        command.add_argument('attempt_id',type=int)
        command.add_argument('--revision',type=int,required=True)
        command.add_argument('--decision-id',type=int,required=True)
        if name=='manual':
            command.add_argument('--score',type=int,required=True)
            command.add_argument('--reason',required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password:
        parser.error('--url harus alamat HTTP(S) tanpa kredensial.')
    with httpx.Client(base_url=args.url,timeout=30,trust_env=False) as client:
        page = client.get('/admin/login')
        page.raise_for_status()
        key = getpass.getpass('Master key admin: ')
        response = client.post('/admin/login',data={'master_key':key,'csrf_token':client.cookies.get('admin_login_csrf','')})
        if response.status_code!=303 or response.headers.get('location')!='/admin':
            raise RuntimeError('Login admin gagal.')
        session = client.get('/api/admin/session')
        session.raise_for_status()
        client.headers['X-CSRF-Token'] = session.json()['csrf_token']
        try:
            if args.command=='list':
                params = {k:v for k,v in {'status':args.status,'before_id':args.before_id}.items() if v is not None}
                response = client.get('/api/admin/grading/jobs',params=params)
            elif args.command=='show':
                response = client.get(f'/api/admin/grading/attempts/{args.attempt_id}')
            else:
                body = {'question_revision':args.revision,'expected_decision_id':args.decision_id}
                if args.command=='manual':
                    body.update(score=args.score,reason=args.reason)
                response = client.post(f'/api/admin/grading/attempts/{args.attempt_id}/{args.command}',json=body)
            if response.status_code>=400:
                raise RuntimeError(f"HTTP {response.status_code}: {response.json().get('detail','Permintaan ditolak.')}")
            print(json.dumps(response.json(),indent=2,ensure_ascii=True))
        finally:
            client.post('/admin/logout')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError,httpx.HTTPError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
