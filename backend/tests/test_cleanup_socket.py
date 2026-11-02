import asyncio
import json
from pathlib import Path
import queue
import os
import unittest
from concurrent.futures import CancelledError as FutureCancelledError
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import psycopg
from psycopg import sql

from tests.test_postgres_api import PostgresApiFixture
from tests.test_files_chat import pdf_bytes, FakeEmbeddings
from api.services.postgres_ingestion import IngestionWorker
from api.services.storage_cleanup import StorageCleanup
from postgres_main import create_app


class FakePubsub:
    def __init__(self):
        self.messages = queue.Queue()

    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def subscribe(self,*args): pass
    async def get_message(self,**kwargs):
        try:
            return {'data':self.messages.get_nowait()}
        except queue.Empty:
            await asyncio.sleep(0.01)
            return None


class CleanupSocketTests(PostgresApiFixture):
    async def course(self):
        self.teacher, self.headers = await self.account('teacher','teacher')
        self.classroom = (await self.client.post('/api/classrooms', headers=self.headers,json={'name':'ML'})).json()
        self.cid = self.classroom['classroom_id']

    async def upload(self):
        response = await self.client.post('/api/upload/file', headers=self.headers,data={'classroom_id':self.cid},
          files={'file':('notes.pdf',pdf_bytes(),'application/pdf')})
        self.assertEqual(response.status_code,202,response.text)
        return response.json()['file_id']

    def cleanup_worker(self):
        with psycopg.connect(self.owner_url) as connection:
            grants = (Path(__file__).parents[1]/'migrations/worker_grants.sql').read_text()
            for statement in grants.split(';'):
                if statement.strip():
                    connection.execute(statement.replace(':"runtime_role"',sql.Identifier(self.role).as_string(connection)))
        return StorageCleanup(self.app.state.accounts.factory,self.storage)

    async def test_document_delete_cancels_work_and_queues_physical_cleanup(self):
        await self.course()
        file_id = await self.upload()
        path = Path((await self.app.state.files.get(self.teacher,file_id))['storage_path'])
        worker = self.cleanup_worker()
        await IngestionWorker(worker.factory,FakeEmbeddings(),self.storage).run_once()
        self.assertEqual((await self.client.get(f'/api/files/{file_id}',headers=self.headers)).json()['processing']['chunk_count'],1)
        response = await self.client.delete(f'/api/files/{file_id}',headers=self.headers)
        self.assertEqual(response.status_code,202,response.text)
        self.assertTrue(path.exists())
        self.assertEqual((await self.client.get(f'/api/files/{file_id}',headers=self.headers)).status_code,404)
        self.assertEqual((await self.client.get(f'/api/files/{file_id}/download',headers=self.headers)).status_code,404)
        with psycopg.connect(self.owner_url) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM ingestion_jobs WHERE file_id=%s',(file_id,)).fetchone()[0],0)
            self.assertEqual(connection.execute('SELECT count(*) FROM chunks WHERE file_id=%s',(file_id,)).fetchone()[0],0)
        self.assertTrue(await worker.run_once())
        self.assertFalse(path.exists())
        self.assertFalse(await worker.run_once())

    async def test_classroom_delete_preserves_cleanup_job_and_restart_is_idempotent(self):
        await self.course()
        file_id = await self.upload()
        path = Path((await self.app.state.files.get(self.teacher,file_id))['storage_path'])
        response = await self.client.delete(f'/api/classrooms/{self.cid}',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        # Simulate the crash window after unlink but before the worker's ack.
        path.unlink()
        worker = self.cleanup_worker()
        self.assertTrue(await worker.run_once())
        with psycopg.connect(self.owner_url) as connection:
            self.assertIsNotNone(connection.execute('SELECT completed_at FROM storage_cleanup WHERE file_id=%s',(file_id,)).fetchone()[0])

    async def test_cleanup_failure_retries_and_outside_path_is_preserved(self):
        await self.course()
        file_id = await self.upload()
        path = Path((await self.app.state.files.get(self.teacher,file_id))['storage_path'])
        await self.client.delete(f'/api/files/{file_id}',headers=self.headers)
        worker = self.cleanup_worker()
        original = Path.unlink
        def deny_delete(target,*args,**kwargs):
            if target == path:
                raise PermissionError('Synthetic locked file')
            return original(target,*args,**kwargs)
        with patch.object(Path,'unlink',deny_delete):
            await worker.run_once()
        self.assertTrue(path.exists())
        with psycopg.connect(self.owner_url) as connection:
            self.assertEqual(connection.execute('SELECT attempts FROM storage_cleanup WHERE file_id=%s',(file_id,)).fetchone()[0],1)
            connection.execute('UPDATE storage_cleanup SET available_at=now() WHERE file_id=%s',(file_id,))
        await worker.run_once()
        self.assertFalse(path.exists())
        protected = Path(self.storage).parent / f'{self.tag}-protected.txt'
        protected.write_text('keep',encoding='utf-8')
        try:
            with psycopg.connect(self.owner_url) as connection:
                connection.execute('INSERT INTO storage_cleanup(file_id,storage_path,actor_id) VALUES (%s,%s,%s)',('bad-'+self.tag,str(protected),self.teacher['user_id']))
            await worker.run_once()
            self.assertTrue(protected.exists())
        finally:
            protected.unlink()

    async def test_websocket_auth_scoping_revocation_and_global_calendar(self):
        await self.course()
        student, student_headers = await self.account('student')
        await self.client.post('/api/classrooms/join',headers=student_headers,json={'join_code':self.classroom['join_code']})
        token = student_headers['Authorization'].split(' ',1)[1]
        app = create_app(self.runtime_url,storage_root=self.storage)
        pubsub = FakePubsub()
        verified=False
        def socket_scenario():
            nonlocal verified
            with TestClient(app,backend_options={'loop_factory':asyncio.SelectorEventLoop}) as client:
                app.state.ws_redis.pubsub = lambda: pubsub
                for url in (f'/ws/classroom/{self.cid}',f'/ws/classroom/{self.cid}?token=bad'):
                    with self.assertRaises(WebSocketDisconnect):
                        with client.websocket_connect(url): pass
                with client.websocket_connect(f'/ws/classroom/{self.cid}?token={token}') as socket:
                    self.assertEqual(socket.receive_json()['type'],'connection_established')
                    pubsub.messages.put(json.dumps({'classroom_id':'other','payload':{'type':'must_not_arrive'}}))
                    pubsub.messages.put(json.dumps({'classroom_id':self.cid,'payload':{'type':'announcement_updated'}}))
                    self.assertEqual(socket.receive_json()['type'],'announcement_updated')
                    socket.send_text('ping')
                    self.assertEqual(socket.receive_text(),'pong')
                    with psycopg.connect(self.owner_url) as connection:
                        connection.execute('DELETE FROM classroom_members WHERE classroom_id=%s AND user_id=%s',(self.cid,student['user_id']))
                    socket.send_text('ping')
                    with self.assertRaises(WebSocketDisconnect) as error:
                        socket.receive_text()
                    self.assertEqual(error.exception.code,4003)
                with client.websocket_connect(f'/ws/classroom/global_events?token={token}') as socket:
                    socket.receive_json()
                    pubsub.messages.put(json.dumps({'classroom_id':self.cid,'payload':{'type':'calendar_updated','event_id':'private'}}))
                    pubsub.messages.put(json.dumps({'classroom_id':'global_events','payload':{'type':'calendar_updated','event_id':'public'}}))
                    self.assertEqual(socket.receive_json()['event_id'],'public')
                    verified=True
        def checked_scenario():
            try:socket_scenario()
            except (FutureCancelledError,asyncio.CancelledError):
                # TestClient can cancel its ASGI future during close. A cancel
                # before all authorization/delivery assertions must still fail.
                if not verified:raise
        await asyncio.to_thread(checked_scenario)

    @unittest.skipUnless(os.getenv('TEST_REDIS_URL'),'Set TEST_REDIS_URL for live Redis gateway integration')
    async def test_real_redis_update_reaches_authenticated_socket(self):
        from redis import Redis
        await self.course()
        token = self.headers['Authorization'].split(' ',1)[1]
        app = create_app(self.runtime_url,storage_root=self.storage,redis_url=os.environ['TEST_REDIS_URL'])
        def scenario():
            publisher = Redis.from_url(os.environ['TEST_REDIS_URL'],socket_timeout=5,socket_connect_timeout=5)
            try:
                with TestClient(app,backend_options={'loop_factory':asyncio.SelectorEventLoop}) as client:
                    verified=False
                    try:
                        with client.websocket_connect(f'/ws/classroom/{self.cid}?token={token}') as socket:
                            self.assertEqual(socket.receive_json()['type'],'connection_established')
                            publisher.publish('classroom_updates',json.dumps({'classroom_id':self.cid,
                              'payload':{'type':'announcement_updated','event_id':'integration-test'}}))
                            self.assertEqual(socket.receive_json()['event_id'],'integration-test')
                            socket.send_text('ping')
                            self.assertEqual(socket.receive_text(),'pong')
                            verified=True
                    except FutureCancelledError:
                        # Starlette can cancel its ASGI future during client close.
                        # Accept that teardown only after every delivery assertion.
                        if not verified:
                            raise
            finally:
                publisher.close()
        await asyncio.to_thread(scenario)
