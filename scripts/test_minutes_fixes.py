"""Numbering conflicts remain recoverable under edit, create races and deleted questions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database as db
import main
from admin_test_support import authenticate_admin
from fastapi.testclient import TestClient


class MinutesFixTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='sqlexam_minutes_fixes_')
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ,{'EXAM_SQLITE_PATH':str(Path(directory.name)/'exam.db'),'ADMIN_MASTER_KEY':'minutes-test-key'})
        env.start()
        self.addCleanup(env.stop)
        postgres = patch.object(db.psycopg2,'connect',side_effect=AssertionError('No production PostgreSQL in unit tests'))
        postgres.start()
        self.addCleanup(postgres.stop)
        db.init_system_db()
        self.a = db.save_question(1,'A question','Description',10,'SELECT 1',category='FIXA')
        self.b = db.save_question(1,'B question','Description',10,'SELECT 1',category='FIXB')
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        authenticate_admin(self.client)
        self.body = dict(question_number=1,title='Moved question',description='Description',score_weight=10,
                         expected_query='SELECT 1',category='FIXB',target_database='pagila')

    def test_create_duplicate_returns_409_and_keeps_both_originals(self):
        response = self.client.post('/api/admin/questions',json=self.body)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['code'],'question_number_conflict')
        self.assertIn('FIXB',response.json()['detail'])
        self.assertEqual(db.get_question_by_id(self.b)['title'],'B question')

    def test_move_collision_rolls_back_without_changing_revision_or_identity(self):
        original = db.get_question_by_id(self.a)
        response = self.client.post('/api/admin/questions',json={**self.body,'question_id':self.a,'expected_edit_revision':original['edit_revision']})
        self.assertEqual(response.status_code,409)
        restored = db.get_question_by_id(self.a)
        self.assertEqual((restored['category'],restored['question_number'],restored['edit_revision']),('FIXA',1,original['edit_revision']))

    def test_valid_move_preserves_id_and_other_package(self):
        original = db.get_question_by_id(self.a)
        response = self.client.post('/api/admin/questions',json={**self.body,'question_number':2,'question_id':self.a,'expected_edit_revision':original['edit_revision']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['id'],self.a)
        moved = db.get_question_by_id(self.a)
        self.assertEqual((moved['category'],moved['question_number']),('FIXB',2))
        self.assertEqual(db.get_question_by_id(self.b)['question_number'],1)

    def test_category_case_cannot_bypass_collision_guard(self):
        response = self.client.post('/api/admin/questions',json={**self.body,'category':'fixb'})
        self.assertEqual(response.status_code,409)

    def test_two_admin_create_race_has_one_winner_and_one_conflict(self):
        def create(number):
            try:
                db.save_question(7,'Concurrent question','Description',10,'SELECT 1',category='RACE')
                return 200
            except db.StudentAccessError as error:
                return error.status_code
        with ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(create,range(2))),[200,409])
        with closing(db.get_sqlite_conn()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM questions WHERE category='RACE'").fetchone()[0],1)

    def test_deleted_question_is_404_instead_of_server_error(self):
        response = self.client.post('/api/admin/questions',json={**self.body,'question_number':2,'question_id':999999,'expected_edit_revision':1})
        self.assertEqual(response.status_code,404,response.text)

    def test_invalid_numbers_are_validation_errors(self):
        for number in (0,-1,True,'1'):
            with self.subTest(number=number):
                self.assertEqual(self.client.post('/api/admin/questions',json={**self.body,'question_number':number}).status_code,422)


if __name__=='__main__':
    unittest.main(verbosity=2)
