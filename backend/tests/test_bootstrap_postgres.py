"""Provisioning must retain credentials and refuse privileged role reuse."""
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from scripts.bootstrap_postgres import provision_role


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'),'Set TEST_DATABASE_URL for provisioning integration')
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.url=os.environ['TEST_DATABASE_URL']
        self.role='bootstrap_test_'+uuid4().hex[:12]
        self.owner=psycopg.connect(self.url)

    def tearDown(self):
        self.owner.rollback()
        self.owner.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(self.role))) if self.owner.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(self.role,)).fetchone() else None
        self.owner.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(self.role)))
        self.owner.commit()
        self.owner.close()

    def test_runtime_role_is_restricted_and_reprovisioning_preserves_password(self):
        credential=provision_role(self.owner,self.role,self.url,None)
        self.owner.commit()
        with psycopg.connect(credential) as runtime:
            flags=runtime.execute('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
            self.assertEqual(flags,(False,False,False,False))
            self.assertEqual(runtime.execute('SELECT count(*) FROM classrooms').fetchone()[0],0)
        self.assertEqual(provision_role(self.owner,self.role,self.url,credential),credential)

    def test_missing_credential_does_not_rotate_an_existing_role(self):
        provision_role(self.owner,self.role,self.url,None)
        self.owner.commit()
        with self.assertRaisesRegex(RuntimeError,'credential is missing'):
            provision_role(self.owner,self.role,self.url,None)

    def test_privileged_role_cannot_become_an_application_login(self):
        self.owner.execute(sql.SQL('CREATE ROLE {} CREATEDB').format(sql.Identifier(self.role)))
        self.owner.commit()
        with self.assertRaisesRegex(RuntimeError,'privileged'):
            provision_role(self.owner,self.role,self.url,None)
