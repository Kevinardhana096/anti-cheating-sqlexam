"""Measured HTTP workload against a new temporary cluster; production URLs are not accepted."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_support import isolated_environment, ROOT
import httpx


def percentile(samples, fraction):
    return round(sorted(samples)[max(0,math.ceil(len(samples)*fraction)-1)],2) if samples else 0


def stage(name, clients, workers, action):
    def run(item):
        started = time.perf_counter()
        try:
            result = action(*item)
        except Exception as error:
            result = {'kind':'unexpected','error_type':type(error).__name__}
        result['ms'] = (time.perf_counter()-started)*1000
        return result
    began = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(run,enumerate(clients)))
    seconds = time.perf_counter()-began
    counts = {}
    for result in results:
        counts[result['kind']] = counts.get(result['kind'],0)+1
    durations = [r['ms'] for r in results]
    record = {'stage':name,'requests':len(clients),'workers':workers,'seconds':round(seconds,3),
              'operations_per_second':round(len(clients)/seconds,2),'outcomes':counts,
              'p50_ms':percentile(durations,.5),'p95_ms':percentile(durations,.95),'p99_ms':percentile(durations,.99),
              'unexpected_errors':[r for r in results if r['kind']=='unexpected']}
    print(json.dumps(record),flush=True)
    return record


def run(students, workers, burst_workers, automatic_drain=False):
    if "database" in sys.modules:
        raise RuntimeError("Jalankan benchmark sebagai proses baru sebelum mengimpor database.")
    results = []
    with isolated_environment() as fixture:
        import database as db
        db.set_exam_state('waiting')
        db.create_package('LOAD','Load fixture','Temporary benchmark',1)
        qid = db.save_question(1,'Complete results fixture','Compare complete results',10,
                               'SELECT n FROM generate_series(1,1000) n',category='LOAD',target_database='pagila')
        with closing(db.get_sqlite_conn()) as conn,conn:
            conn.execute("UPDATE exam_packages SET is_active=(code='LOAD')")
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port = listener.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        log = (fixture/'uvicorn.log').open('w',encoding='utf-8')
        server = subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port)],
                                  cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        clients = []
        try:
            with httpx.Client(base_url=base,timeout=30,trust_env=False) as admin:
                deadline = time.monotonic()+60
                while True:
                    try:
                        if admin.get('/health').status_code==200:
                            break
                    except httpx.HTTPError:
                        pass
                    if server.poll() is not None or time.monotonic()>=deadline:
                        raise RuntimeError('Temporary HTTP server failed to start.')
                    time.sleep(.2)
                clients = [httpx.Client(base_url=base,timeout=30,trust_env=False) for _ in range(students)]
                def login(index,client):
                    response = client.post('/login',data={'nim':f'LOAD{index:03}','name':f'Load Student {index}','device_id':f'load-device-{index}'})
                    return {'kind':'ok' if response.status_code==302 and client.cookies.get('student_token') else 'unexpected', 'status':response.status_code}
                results.append(stage('shared_ip_login',clients,burst_workers,login))
                admin.get('/admin/login')
                response = admin.post('/admin/login',data={'master_key':os.environ['ADMIN_MASTER_KEY'],
                                                          'csrf_token':admin.cookies.get('admin_login_csrf')})
                if response.status_code!=303:
                    raise RuntimeError('Fixture admin login failed.')
                admin.headers['X-CSRF-Token'] = admin.get('/api/admin/session').json()['csrf_token']
                response = admin.post('/api/admin/exam/validate')
                if response.status_code!=200:
                    raise RuntimeError('Fixture reference validation failed.')
                response = admin.post('/api/admin/exam/start')
                if response.status_code!=200:
                    raise RuntimeError('Fixture reference validation/start failed.')
                def payload(index,client):
                    return {'nim':f'LOAD{index:03}','session_token':client.cookies.get('student_token')}
                for index,client in enumerate(clients):
                    response = client.post('/api/student/select-category',json={**payload(index,client),'category':'LOAD'})
                    if response.status_code!=200:
                        raise RuntimeError('Fixture package selection failed.')
                def preview(index,client,sandbox=False):
                    query = 'CREATE TABLE IF NOT EXISTS bench(id INT PRIMARY KEY); SELECT count(*) AS total FROM bench' if sandbox else 'SELECT a.actor_id, count(*) AS films FROM actor a JOIN film_actor fa ON fa.actor_id=a.actor_id GROUP BY a.actor_id ORDER BY a.actor_id'
                    response = client.post('/api/student/run-query',json={**payload(index,client),'query':query,
                                           'active_database':'sandbox_pribadi' if sandbox else 'pagila'})
                    data = response.json()
                    return {'kind':'ok' if response.status_code==200 and data.get('success') else 'unexpected', 'status':response.status_code}
                results.append(stage('master_preview',clients,workers,preview))
                results.append(stage('sandbox_cold_preview',clients,workers,lambda i,c:preview(i,c,True)))
                def submit(index,client):
                    response = client.post('/api/student/submit',json={**payload(index,client),'question_id':qid,
                        'query':'SELECT n FROM generate_series(1,1000) n','active_database':'pagila'})
                    data = response.json()
                    kind = 'unexpected'
                    if response.status_code==200:
                        if data.get('graded') and data.get('latest_attempt',{}).get('is_correct')==1:
                            kind = 'graded_correct'
                        elif data.get('graded') is False and data.get('eval_status')=='evaluation_limit':
                            kind = 'pending_limit'
                    return {'kind':kind,'status':response.status_code}
                paced = stage('paced_full_grading',clients,workers,submit)
                results.append(paced)
                results.append(stage('burst_full_grading',clients,burst_workers,submit))
                if automatic_drain:
                    admin.post('/api/admin/exam/stop')
                    began = time.perf_counter()
                    deadline = time.monotonic()+60
                    while True:
                        counts = admin.get('/api/admin/grading/jobs').json()['counts']
                        if not counts.get('queued',0) and not counts.get('running',0):
                            break
                        if time.monotonic()>deadline:
                            raise RuntimeError('Antrean otomatis tidak selesai dalam 60 detik.')
                        time.sleep(.25)
                    drained = {'stage':'automatic_queue_drain_after_stop','seconds':round(time.perf_counter()-began,3),
                               'outcomes':counts,'unexpected_errors':[] if not counts.get('review',0) and not counts.get('stale',0) else [{'kind':'unexpected'}]}
                    results.append(drained)
                    print(json.dumps(drained),flush=True)
                else:
                    results.append(stage('paced_retry_grading',clients,min(workers,4),submit))
                diagnostics = admin.get('/api/admin/diagnostics').json()
                integrity = []
                for index,client in enumerate(clients):
                    if automatic_drain:
                        with closing(db.get_sqlite_conn()) as conn:
                            user_id = conn.execute('SELECT id FROM users WHERE nim=?',(f'LOAD{index:03}',)).fetchone()[0]
                        best = db.get_student_submissions(user_id).get(qid,{})
                    else:
                        data = client.get('/api/student/questions').json()
                        best = data.get('submissions',{}).get(str(qid),{})
                    integrity.append(best.get('score')==10 and best.get('is_correct')==1 and (not automatic_drain or best.get('latest_attempt',{}).get('graded')==1))
                admin.post('/api/admin/exam/stop')
                after_stop = stage('submit_after_stop',clients,workers,lambda i,c:{'kind':'blocked' if c.post('/api/student/submit',json={**payload(i,c),'question_id':qid,'query':'SELECT 1'}).status_code==403 else 'unexpected'})
                results.append(after_stop)
                with closing(db.get_pg_admin_connection()) as conn,conn.cursor() as cursor:
                    cursor.execute('SHOW server_version')
                    pg_version = cursor.fetchone()[0]
                with closing(db.get_sqlite_conn()) as conn:
                    pending_null = conn.execute('SELECT COUNT(*) FROM submission_attempts WHERE graded=0 AND (score IS NOT NULL OR is_correct IS NOT NULL)').fetchone()[0]==0
                return {'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        'environment':{'os':platform.platform(),'python':platform.python_version(),'logical_cpus':os.cpu_count(),
                                       'postgres':pg_version,'http_server':'uvicorn, one process','fixture_fsync':False},
                        'automatic_drain':automatic_drain,'students':students,'stages':results,'all_best_scores_preserved':all(integrity),
                        'pending_attempts_have_null_scores':pending_null,'diagnostics':diagnostics,
                        'passed':all(not r['unexpected_errors'] for r in results) and all(integrity) and pending_null,
                        'limits':'Synthetic loopback workload, not a production class-capacity guarantee.'}
        finally:
            for client in clients:
                client.close()
            server.terminate()
            server.wait(timeout=15)
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--students',type=int,default=24)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--burst-workers',type=int,default=24)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--automatic-drain',action='store_true')
    args = parser.parse_args()
    if not 1<=args.students<=80 or not 1<=args.workers<=32 or not 1<=args.burst_workers<=80:
        parser.error('students/burst-workers: 1..80; workers: 1..32.')
    if args.output.exists():
        parser.error('Output harus berkas baru agar hasil pengukuran tidak tertimpa.')
    result = run(args.students,args.workers,args.burst_workers,args.automatic_drain)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
