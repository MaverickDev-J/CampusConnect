"""Fresh-database administration and private expiring guest sessions."""
import os
from unittest.mock import patch

import psycopg

from core.security import decode_access_token
from tests.test_postgres_api import PostgresApiFixture


class AdminDemoTests(PostgresApiFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.guests=[]

    async def asyncTearDown(self):
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('DELETE FROM users WHERE user_id=ANY(%s)',(self.guests,))
        await super().asyncTearDown()

    async def admin(self):
        self.administrator,self.headers=await self.account('administrator','teacher')
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE users SET role='superadmin' WHERE user_id=%s",(self.administrator['user_id'],))

    async def test_admin_provision_list_delete_and_live_role_revocation(self):
        await self.admin()
        _,student=await self.account('student')
        self.assertEqual((await self.client.get('/api/superadmin/users',headers=student)).status_code,403)
        body={'email':'new-teacher'+self.tag+'@example.com','name':'New teacher','password':'safe-new-password'}
        response=await self.client.post('/api/superadmin/provision-teacher',headers=self.headers,json=body)
        self.assertEqual(response.status_code,201,response.text)
        teacher=response.json()
        self.assertEqual(teacher['role'],'teacher')
        self.assertNotIn('password',teacher)
        self.assertEqual((await self.client.post('/api/superadmin/provision-teacher',headers=self.headers,json=body)).status_code,409)
        listing=(await self.client.get('/api/superadmin/users',headers=self.headers,params={'role':'teacher'})).json()
        self.assertTrue(any(row['user_id']==teacher['user_id'] for row in listing['users']))
        self.assertTrue(all('password_hash' not in row for row in listing['users']))
        self.assertEqual((await self.client.delete('/api/superadmin/users/'+self.administrator['user_id'],headers=self.headers)).status_code,400)
        self.assertEqual((await self.client.delete('/api/superadmin/users/'+teacher['user_id'],headers=self.headers)).status_code,200)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE users SET role='student' WHERE user_id=%s",(self.administrator['user_id'],))
        self.assertEqual((await self.client.get('/api/superadmin/users',headers=self.headers)).status_code,403)

    async def test_deletion_does_not_silently_erase_owned_classrooms(self):
        await self.admin()
        teacher,headers=await self.account('owner','teacher')
        classroom=(await self.client.post('/api/classrooms',headers=headers,json={'name':'Keep course'})).json()
        response=await self.client.delete('/api/superadmin/users/'+teacher['user_id'],headers=self.headers)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual((await self.client.get('/api/classrooms/'+classroom['classroom_id'],headers=headers)).status_code,200)

    async def test_demo_is_disabled_or_unready_without_automatic_seeding(self):
        with patch.dict(os.environ,{'DEMO_ENABLED':'false'}):
            self.assertEqual((await self.client.post('/api/auth/demo-login')).status_code,503)
        with patch.dict(os.environ,{'DEMO_ENABLED':'true'}):
            self.assertEqual((await self.client.post('/api/auth/demo-login')).status_code,503)

    async def test_demo_guests_have_private_sessions_and_expire_in_database(self):
        teacher,_=await self.account('curator','teacher')
        with psycopg.connect(self.owner_url) as conn:
            if conn.execute("SELECT 1 FROM classrooms WHERE classroom_id='cls_demo_sandbox'").fetchone():
                self.skipTest('Demo fixture ID is in use; choose a disposable test database')
            conn.execute("INSERT INTO classrooms(classroom_id,name,join_code,created_by) VALUES ('cls_demo_sandbox','Demo','DEMO01',%s)",(teacher['user_id'],))
            file_id='demo-fixture-'+self.tag
            conn.execute("INSERT INTO files(file_id,classroom_id,original_name,storage_path,file_type,sha256_hash,uploaded_by,status) VALUES (%s,'cls_demo_sandbox','Demo','/test','pdf',%s,%s,'ready')",(file_id,self.tag,teacher['user_id']))
            conn.execute("INSERT INTO file_revisions VALUES (%s,1,'gemini-embedding-2:1536:search-v1','test','ready')",(file_id,))
            conn.execute('UPDATE files SET active_revision=1 WHERE file_id=%s',(file_id,))
        tokens=[]
        with patch.dict(os.environ,{'DEMO_ENABLED':'true'}):
            for _ in range(2):
                response=await self.client.post('/api/auth/demo-login')
                self.assertEqual(response.status_code,200,response.text)
                token=response.json()['access_token']
                self.guests.append(decode_access_token(token)['user_id'])
                tokens.append({'Authorization':'Bearer '+token})
        self.assertNotEqual(self.guests[0],self.guests[1])
        session=(await self.client.post('/api/chat/sessions',headers=tokens[0],json={'classroom_id':'cls_demo_sandbox'})).json()
        self.assertEqual((await self.client.get('/api/chat/sessions/'+session['session_id']+'/history',headers=tokens[1])).status_code,404)
        self.assertEqual((await self.client.get('/api/users/me',headers=tokens[0])).json()['profile']['is_demo'],True)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE users SET demo_expires_at=now()-interval '1 second' WHERE user_id=%s",(self.guests[0],))
        self.assertEqual((await self.client.get('/api/users/me',headers=tokens[0])).status_code,401)
