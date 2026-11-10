"""NAT admission, bounded login, and public/private operational diagnostics."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database as db
import main
from admin_test_support import authenticate_admin
from fastapi.testclient import TestClient


class OperationalControlTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='sqlexam_controls_')
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ,{'EXAM_SQLITE_PATH':str(Path(directory.name)/'exam.db'),'ADMIN_MASTER_KEY':'ops-control-key'})
        env.start()
        self.addCleanup(env.stop)
        for attribute,value in (('ALLOW_SHARED_IP',True),):
            context = patch.object(db,attribute,value)
            context.start()
            self.addCleanup(context.stop)
        postgres = patch.object(db.psycopg2,'connect',side_effect=AssertionError('No production PostgreSQL'))
        postgres.start()
        self.addCleanup(postgres.stop)
        limiter = patch.object(main,'rate_limiter',main.InMemoryRateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)
        db.init_system_db()
        self.client = self.make_client()

    def make_client(self):
        client = TestClient(main.app)
        self.addCleanup(client.close)
        return client

    def test_twenty_four_students_can_login_from_shared_ip(self):
        for number in range(24):
            client = self.make_client()
            response = client.post('/login',data={'nim':f'NAT{number:03}','name':f'Student {number}','device_id':f'device-{number}'},follow_redirects=False)
            self.assertEqual(response.status_code,302,response.text)
            self.assertIsNotNone(client.cookies.get('student_token'))

    def test_one_identity_is_still_rate_limited(self):
        payload = {'nim':'RATE01','name':'Limited Student','device_id':'rate-device'}
        for _ in range(6):
            self.assertEqual(self.client.post('/login',data=payload,follow_redirects=False).status_code,302)
        self.assertEqual(self.client.post('/login',data=payload,follow_redirects=False).status_code,429)

    def test_public_readiness_excludes_private_details_and_pool(self):
        health = {'sqlite':True,'postgres_admin':False,'postgres_student':False,'databases':{},'details':{'error':'private connection details'}}
        with patch.object(db,'verify_system_health',return_value=health):
            response = self.client.get('/ready')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private connection details',response.text)
        self.assertNotIn('pool',response.json())

    def test_private_diagnostics_requires_admin(self):
        self.assertEqual(self.client.get('/api/admin/diagnostics').status_code,403)
        authenticate_admin(self.client)
        with patch.object(db,'verify_system_health',return_value={'sqlite':True}):
            response = self.client.get('/api/admin/diagnostics')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['limits']['grading_slots_per_process'],4)


if __name__=='__main__':
    unittest.main(verbosity=2)
