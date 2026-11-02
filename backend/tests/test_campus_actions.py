import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import psycopg
from psycopg import sql
from sqlalchemy import text

from tests.test_postgres_api import PostgresApiFixture
from api.routers.announcements import CreateAnnouncementBody
from api.routers.postgres_campus import EventBody
from api.services.campus_outbox import CampusOutbox


class CampusActionTests(PostgresApiFixture):
    async def course(self):
        self.teacher, self.headers = await self.account('teacher', 'teacher')
        self.student, self.student_headers = await self.account('student')
        self.classroom = (await self.client.post('/api/classrooms', headers=self.headers, json={'name':'ML'})).json()
        self.cid = self.classroom['classroom_id']
        await self.client.post('/api/classrooms/join', headers=self.student_headers, json={'join_code':self.classroom['join_code']})

    async def test_announcement_retry_notifications_and_access(self):
        await self.course()
        body = {'classroom_id':self.cid, 'content':'Unit 3 revision'}
        headers = {**self.headers, 'Idempotency-Key':'announcement-1'}
        first, second = await asyncio.gather(*(self.client.post('/api/announcements', headers=headers, json=body) for _ in range(2)))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json(), second.json())
        listing = (await self.client.get(f'/api/announcements/{self.cid}', headers=self.student_headers)).json()
        self.assertEqual(listing['total'], 1)
        notes = (await self.client.get('/api/notifications', headers=self.student_headers)).json()
        self.assertEqual(notes['count'], 1)
        note_id = notes['notifications'][0]['notification_id']
        self.assertEqual((await self.client.get('/api/notifications', headers=self.headers)).json()['count'], 0)
        self.assertEqual((await self.client.patch(f'/api/notifications/{note_id}/read', headers=self.headers)).status_code, 404)
        self.assertEqual((await self.client.patch(f'/api/notifications/{note_id}/read', headers=self.student_headers)).status_code, 200)
        self.assertEqual((await self.client.get('/api/notifications', headers=self.student_headers)).json()['count'], 0)
        changed = await self.client.post('/api/announcements', headers=headers, json={**body,'content':'Different'})
        self.assertEqual(changed.status_code, 409)
        self.assertEqual((await self.client.post('/api/announcements', headers=self.student_headers, json=body)).status_code, 403)
        _, outsider = await self.account('outsider', 'teacher')
        self.assertIn((await self.client.post('/api/announcements', headers=outsider, json=body)).status_code, (403,404))
        resource = first.json()['announcement_id']
        self.assertIn((await self.client.delete(f'/api/announcements/{resource}', headers=outsider)).status_code, (403,404))
        self.assertEqual((await self.client.delete(f'/api/announcements/{resource}', headers=self.headers)).status_code, 200)

    async def test_calendar_validation_scope_and_global_admin(self):
        await self.course()
        body = {'classroom_id':self.cid, 'title':'Revision', 'date':'2026-11-06', 'type':'event'}
        event = await self.client.post('/api/calendar/events', headers=self.headers, json=body)
        self.assertEqual(event.status_code, 201, event.text)
        rows = (await self.client.get('/api/calendar/events', headers=self.student_headers)).json()['events']
        self.assertEqual(rows[0]['date'], '2026-11-06')
        self.assertEqual(rows[0]['classroom_name'], 'ML')
        self.assertEqual((await self.client.post('/api/calendar/events', headers=self.headers, json={**body,'date':'wrong'})).status_code, 422)
        self.assertEqual((await self.client.post('/api/calendar/events', headers=self.headers, json={**body,'type':'anything'})).status_code, 422)
        self.assertEqual((await self.client.post('/api/calendar/events', headers=self.headers, json={**body,'classroom_id':None})).status_code, 403)
        admin, admin_headers = await self.account('admin', 'teacher')
        with psycopg.connect(self.owner_url) as connection:
            connection.execute("UPDATE users SET role='superadmin' WHERE user_id=%s", (admin['user_id'],))
        global_event = await self.client.post('/api/calendar/events', headers=admin_headers, json={**body,'classroom_id':None})
        self.assertEqual(global_event.status_code, 201, global_event.text)
        rows = (await self.client.get('/api/calendar/events', headers=self.student_headers)).json()['events']
        self.assertEqual(len(rows), 2)
        _, other = await self.account('other', 'teacher')
        rows = (await self.client.get('/api/calendar/events', headers=other)).json()['events']
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['classroom_id'])
        self.assertEqual((await self.client.delete(f"/api/calendar/events/{event.json()['event_id']}", headers=self.headers)).status_code, 200)

    async def test_revision_actions_are_atomic_and_replay_safe(self):
        await self.course()
        service = self.app.state.actions
        announcement = CreateAnnouncementBody(classroom_id=self.cid, content='Revision notes')
        event = EventBody(classroom_id=self.cid, title='Revision', date='2026-11-06')
        async def fail_after_first_write(*args):
            raise RuntimeError('Synthetic database failure')
        with patch.object(service, '_calendar', side_effect=fail_after_first_write):
            with self.assertRaises(RuntimeError):
                await service.revision_session(self.teacher, announcement, event, 'approved-revision')
        self.assertEqual((await self.client.get(f'/api/announcements/{self.cid}', headers=self.headers)).json()['total'], 0)
        self.assertEqual((await self.client.get('/api/notifications', headers=self.student_headers)).json()['count'], 0)
        results = await asyncio.gather(*(service.revision_session(self.teacher, announcement, event, 'approved-revision') for _ in range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual((await self.client.get('/api/calendar/events', headers=self.headers)).json()['events'][0]['event_id'], results[0]['event']['event_id'])
        self.assertEqual((await self.client.get('/api/notifications', headers=self.student_headers)).json()['count'], 2)
        await self.client.delete('/api/notifications/clear', headers=self.student_headers)
        self.assertEqual((await self.client.get('/api/notifications', headers=self.student_headers)).json()['count'], 0)

    async def test_outbox_retry_and_delivery(self):
        await self.course()
        response=await self.client.post('/api/announcements', headers=self.headers, json={'classroom_id':self.cid,'content':'Update'})
        self.assertEqual(response.status_code,201,response.text)
        with psycopg.connect(self.owner_url) as connection:
            grants = (Path(__file__).parents[1]/'migrations/worker_grants.sql').read_text()
            for statement in grants.split(';'):
                if statement.strip():
                    connection.execute(statement.replace(':"runtime_role"', sql.Identifier(self.role).as_string(connection)))
            # Make the fixture unambiguously due; this checks failure/retry,
            # rather than timing the initial enqueue/claim boundary.
            connection.execute("UPDATE campus_outbox SET available_at=now()-interval '1 second' WHERE actor_id=%s",(self.teacher['user_id'],))
        publish = AsyncMock(side_effect=RuntimeError('Redis unavailable'))
        dispatcher = CampusOutbox(self.app.state.accounts.factory, publish)
        self.assertTrue(await dispatcher.run_once())
        with psycopg.connect(self.owner_url) as connection:
            row = connection.execute('SELECT delivered_at,attempts FROM campus_outbox WHERE actor_id=%s', (self.teacher['user_id'],)).fetchone()
            self.assertEqual(row, (None,1))
            connection.execute('UPDATE campus_outbox SET available_at=now() WHERE actor_id=%s', (self.teacher['user_id'],))
        publish.side_effect = None
        self.assertTrue(await dispatcher.run_once())
        self.assertFalse(await dispatcher.run_once())
        publish.assert_awaited()
        self.assertEqual(publish.call_args.args[0], self.cid)
