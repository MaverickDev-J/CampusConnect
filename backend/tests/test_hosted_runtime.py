"""Verify durability ordering, streaming-volume exclusion and job recovery hooks."""
import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

import psycopg
from core.hosted_runtime import VolumeRequests,WakeJobs,drain
from scripts.configure_modal import runtime_secrets
from tests.test_postgres_api import PostgresApiFixture


async def receive():
    return {'type':'http.request','body':b''}


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_volume_reload_waits_until_download_stream_has_closed(self):
        opened,release=asyncio.Event(),asyncio.Event()
        reload=AsyncMock()
        async def stream(scope,receive,send):
            opened.set()
            await release.wait()
        middleware=VolumeRequests(stream,reload=reload)
        scope={'type':'http','path':'/api/files/a/download'}
        first=asyncio.create_task(middleware(scope,receive,AsyncMock()))
        await opened.wait()
        second=asyncio.create_task(middleware(scope,receive,AsyncMock()))
        await asyncio.sleep(0)
        self.assertEqual(reload.await_count,1)
        release.set()
        await asyncio.gather(first,second)
        self.assertEqual(reload.await_count,2)

    async def test_wake_is_awaited_after_success_and_failure_leaves_committed_response(self):
        wake=AsyncMock(side_effect=RuntimeError('offline'))
        async def endpoint(scope,receive,send):
            await send({'type':'http.response.start','status':202})
            await send({'type':'http.response.body','body':b'queued'})
        sent=AsyncMock()
        middleware=WakeJobs(endpoint,wake=wake)
        await middleware({'type':'http','method':'POST','path':'/api/upload/file'},receive,sent)
        wake.assert_awaited_once_with('ingestion')
        self.assertEqual(sent.await_args_list[-1].args[0]['body'],b'queued')
        wake.reset_mock()
        await middleware({'type':'http','method':'POST','path':'/api/auth/login'},receive,sent)
        wake.assert_not_awaited()

    async def test_failed_request_never_enqueues_and_drain_exits_on_empty(self):
        wake=AsyncMock()
        async def denied(scope,receive,send):
            await send({'type':'http.response.start','status':403})
        await WakeJobs(denied,wake=wake)({'type':'http','method':'DELETE','path':'/api/files/a'},receive,AsyncMock())
        wake.assert_not_awaited()
        worker=AsyncMock()
        worker.run_once.side_effect=[True,False]
        self.assertEqual(await drain(worker),1)
        self.assertEqual(worker.run_once.await_count,2)

    def test_secrets_separate_worker_owner_and_local_service_credentials(self):
        values={'DATABASE_URL':'postgresql://api@host/db','WORKER_DATABASE_URL':'postgresql://worker@host/db',
                'MIGRATION_DATABASE_URL':'postgresql://owner@host/db','JWT_SECRET':'secret',
                'REDIS_URL':'redis://127.0.0.1:6380','GEMINI_API_KEY':'key','MONGO_URI':'legacy'}
        api,worker=runtime_secrets(values,'https://frontend.example.com')
        self.assertEqual(worker['DATABASE_URL'],values['WORKER_DATABASE_URL'])
        self.assertEqual(api['DATABASE_URL'],values['DATABASE_URL'])
        for secret in (api,worker):
            for excluded in ('MIGRATION_DATABASE_URL','WORKER_DATABASE_URL','MONGO_URI','REDIS_URL'):
                self.assertNotIn(excluded,secret)


class DurableUploadTests(PostgresApiFixture):
    async def test_storage_failure_cannot_commit_a_job_before_bytes_are_durable(self):
        user,headers=await self.account('durability','teacher')
        classroom=(await self.client.post('/api/classrooms',headers=headers,json={'name':'Durability'})).json()
        calls=[]
        async def persist():
            with psycopg.connect(self.owner_url) as conn:
                count=conn.execute('SELECT count(*) FROM files WHERE classroom_id=%s',(classroom['classroom_id'],)).fetchone()[0]
                calls.append(count)
            self.assertTrue(any((Path(self.storage)/'uploads').iterdir()))
            raise OSError('Simulated volume commit failure')
        self.app.state.persist_upload=persist
        with self.assertRaises(OSError):
            await self.client.post('/api/upload/file',headers=headers,data={'classroom_id':classroom['classroom_id']},
                files={'file':('notes.pdf',b'content','application/pdf')})
        self.assertEqual(calls,[0])
        with psycopg.connect(self.owner_url) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM files WHERE classroom_id=%s',(classroom['classroom_id'],)).fetchone()[0],0)
        self.assertEqual(list((Path(self.storage)/'uploads').iterdir()),[])

    async def test_hosted_origin_applies_to_cors_and_websockets(self):
        from unittest.mock import patch
        from postgres_main import create_app
        with patch.dict('os.environ',{'CORS_ORIGINS':'https://campus.example.com'}):
            app=create_app(self.runtime_url)
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.options('/api/users/me',headers={'Origin':'https://campus.example.com',
                'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization'})
            self.assertEqual(response.headers['access-control-allow-origin'],'https://campus.example.com')
            rejected=await client.options('/api/users/me',headers={'Origin':'https://untrusted.example.com',
                'Access-Control-Request-Method':'GET'})
            self.assertEqual(rejected.status_code,400)
