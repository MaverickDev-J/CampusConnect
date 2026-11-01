"""Cache invalidation, scoped operational traces and reproducible ranking reports."""
import json
import asyncio
from unittest.mock import AsyncMock

import psycopg
from psycopg import sql

from api.agent.postgres_graph import PostgresRag
from tests import test_files_chat as file_helpers
from tests.test_files_chat import FakeEmbeddings,rag_route
from tests.test_postgres_api import PostgresApiFixture
from api.routers.quality import metrics


class QualityCacheTests(PostgresApiFixture):
    setup_course=file_helpers.FilesChatTests.setup_course
    upload=file_helpers.FilesChatTests.upload
    worker=file_helpers.FilesChatTests.worker

    async def prepared(self):
        await self.setup_course()
        self.file_id=(await self.upload()).json()['file_id']
        await (await self.worker()).run_once()
        self.route=AsyncMock(side_effect=rag_route)
        self.app.state.rag=PostgresRag(self.app.state.accounts.factory,FakeEmbeddings(),route=self.route,cache=self.app.state.answer_cache)
        self.answers=0
        async def answer(state):
            self.answers+=1
            yield 'Verified answer '+str(self.answers)
        self.app.state.answer=answer

    async def ask(self,headers=None,*,file_id=None,session_id=None):
        headers=headers or self.headers
        if not session_id:
            session_id=(await self.client.post('/api/chat/sessions',headers=headers,
                json={'classroom_id':self.cid,'file_id':file_id})).json()['session_id']
        response=await self.client.post('/api/chat/sessions/'+session_id+'/message',headers=headers,
            json={'query':'PRIVATE_QUESTION_123'})
        return session_id,response

    async def test_exact_cache_skips_models_and_dashboard_matches_durable_traces(self):
        await self.prepared()
        _,first=await self.ask()
        _,second=await self.ask()
        self.assertEqual(self.answers,1)
        self.assertEqual(self.route.await_count,1)
        self.assertIn('Verified answer 1',first.text)
        self.assertIn('Verified answer 1',second.text)
        overview=(await self.client.get('/api/quality/overview',params={'classroom_id':self.cid,'kind':'chat'},headers=self.headers)).json()
        self.assertEqual((overview['requests'],overview['cache_hits']),(2,1))
        self.assertIsNone(overview['usage']['input_tokens'])
        runs=(await self.client.get('/api/quality/runs',params={'classroom_id':self.cid},headers=self.headers)).json()['runs']
        self.assertNotIn('PRIVATE_QUESTION_123',json.dumps(runs))
        self.assertTrue(any(run['cache_status']=='exact' for run in runs))

    async def test_benchmark_chat_bypasses_cache_and_requires_faculty(self):
        await self.prepared()
        await self.ask()
        session=(await self.client.post('/api/chat/sessions',headers=self.headers,json={'classroom_id':self.cid})).json()['session_id']
        for _ in range(2):
            response=await self.client.post('/api/chat/sessions/'+session+'/message',headers=self.headers,
                json={'query':'PRIVATE_QUESTION_123','origin':'benchmark','bypass_cache':True})
            self.assertEqual(response.status_code,200,response.text)
            self.assertNotIn('"t": "error"',response.text)
        self.assertEqual(self.answers,3)
        overview=(await self.client.get('/api/quality/overview',params={'classroom_id':self.cid,'origin':'benchmark','kind':'chat'},headers=self.headers)).json()
        self.assertEqual((overview['requests'],overview['cache_hits']),(2,0))
        _,student_headers=await self.account('benchmark-student')
        rejected=await self.client.post('/api/chat/sessions/'+session+'/message',headers=student_headers,
            json={'query':'test','origin':'benchmark'})
        self.assertEqual(rejected.status_code,403)

    async def test_corpus_changes_expiry_and_deleted_sources_invalidate_reuse(self):
        await self.prepared()
        await self.ask()
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE answer_cache SET expires_at=now()-interval '1 second' WHERE actor_id=%s",(self.teacher['user_id'],))
        await self.ask()
        self.assertEqual(self.answers,2)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE chunks SET content_hash='new-revision-content' WHERE file_id=%s",(self.file_id,))
        await self.ask()
        self.assertEqual(self.answers,3)
        await self.client.delete('/api/files/'+self.file_id,headers=self.headers)
        _,response=await self.ask()
        self.assertEqual(self.answers,4)
        self.assertNotIn(self.file_id,response.text)

    async def test_principal_file_scope_and_history_never_share_an_answer(self):
        await self.prepared()
        sid,_=await self.ask()
        await self.ask(session_id=sid)
        await self.ask(file_id=self.file_id)
        student,headers=await self.account('cache-student')
        await self.client.post('/api/classrooms/join',headers=headers,json={'join_code':self.classroom['join_code']})
        student_sid,_=await self.ask(headers)
        self.assertEqual(self.answers,4)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('DELETE FROM classroom_members WHERE classroom_id=%s AND user_id=%s',(self.cid,student['user_id']))
        response=await self.client.post('/api/chat/sessions/'+student_sid+'/message',headers=headers,json={'query':'PRIVATE_QUESTION_123'})
        self.assertEqual(response.status_code,404)

    async def test_cache_and_telemetry_permission_failure_do_not_break_chat(self):
        await self.prepared()
        with psycopg.connect(self.owner_url) as conn:
            conn.execute(sql.SQL('REVOKE ALL ON answer_cache FROM {}').format(sql.Identifier(self.role)))
            conn.execute(sql.SQL('REVOKE INSERT ON ai_runs FROM {}').format(sql.Identifier(self.role)))
        _,response=await self.ask()
        self.assertIn('Verified answer 1',response.text)
        self.assertNotIn('"t": "error"',response.text)

    async def test_comparison_report_uses_saved_rankings_and_separates_origins(self):
        await self.prepared()
        response=await self.client.post('/api/quality/compare',headers=self.headers,
            json={'classroom_id':self.cid,'query':'backpropagation','origin':'benchmark'})
        self.assertEqual(response.status_code,200,response.text)
        comparison=response.json()
        cid=comparison['strategies']['hybrid']['candidate_ids'][0]
        body={'classroom_id':self.cid,'dataset_version':'synthetic-v1','reviewed':False,
              'cases':[{'case_id':'exact-1','run_id':comparison['run_id'],'relevant_chunk_ids':[cid]}]}
        report=await self.client.post('/api/quality/evaluations',headers=self.headers,json=body)
        self.assertEqual(report.status_code,201,report.text)
        self.assertEqual(report.json()['label_status'],'provisional')
        self.assertFalse(report.json()['generation_evaluated'])
        self.assertEqual(report.json()['summary']['hybrid']['recall_at_12'],1)
        self.assertEqual(report.json()['summary']['hybrid_rerank']['fallback_cases'],1)
        overview=(await self.client.get('/api/quality/overview',headers=self.headers,params={'classroom_id':self.cid,'kind':'comparison'})).json()
        self.assertEqual(overview['requests'],0)
        overview=(await self.client.get('/api/quality/overview',headers=self.headers,params={'classroom_id':self.cid,'origin':'benchmark','kind':'comparison'})).json()
        self.assertEqual(overview['requests'],1)
        self.assertEqual(len((await self.client.get('/api/quality/evaluations',headers=self.headers,params={'classroom_id':self.cid})).json()['evaluations']),1)
        # Changed corpora cannot be compared against old labels/run snapshots.
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE files SET original_name='Updated notes' WHERE file_id=%s",(self.file_id,))
        self.assertEqual((await self.client.post('/api/quality/evaluations',headers=self.headers,json=body)).status_code,409)

    async def test_quality_scope_and_unavailable_metrics_fail_truthfully(self):
        await self.prepared()
        student,headers=await self.account('quality-student')
        await self.client.post('/api/classrooms/join',headers=headers,json={'join_code':self.classroom['join_code']})
        self.assertEqual((await self.client.get('/api/quality/runs',headers=headers,params={'classroom_id':self.cid})).status_code,403)
        _,outsider=await self.account('quality-outsider','teacher')
        self.assertIn((await self.client.get('/api/quality/runs',headers=outsider,params={'classroom_id':self.cid})).status_code,(403,404))
        self.app.state.rag.embeddings.query=AsyncMock(side_effect=RuntimeError('Unavailable'))
        comparison=(await self.client.post('/api/quality/compare',headers=self.headers,
            json={'classroom_id':self.cid,'query':'backpropagation','origin':'synthetic'})).json()
        self.assertEqual(comparison['strategies']['dense']['status'],'unavailable')
        self.assertEqual(comparison['strategies']['hybrid']['strategy'],'lexical')
        report=(await self.client.post('/api/quality/evaluations',headers=self.headers,json={'classroom_id':self.cid,
            'dataset_version':'unavailable-v1','cases':[{'case_id':'q1','run_id':comparison['run_id'],
                'relevant_chunk_ids':[comparison['strategies']['hybrid']['candidate_ids'][0]]}]})).json()
        self.assertIsNone(report['summary']['dense']['ndcg_at_6'])
        self.assertIsNone(metrics([],[])['recall_at_12'])

    async def test_corpus_invalidation_does_not_wait_on_classroom_delete_lock(self):
        await self.prepared()
        # Deletion locks the classroom then waits for ingestion. A writer holding
        # the ingestion row must finish invalidation without needing that lock.
        writer=await psycopg.AsyncConnection.connect(self.runtime_url)
        deleter=await psycopg.AsyncConnection.connect(self.runtime_url)
        try:
            for conn in (writer,deleter):
                await conn.execute("SELECT set_config('app.user_id',%s,true)",(self.teacher['user_id'],))
            await writer.execute('SELECT file_id FROM ingestion_jobs WHERE file_id=%s FOR UPDATE',(self.file_id,))
            await deleter.execute('SELECT classroom_id FROM classrooms WHERE classroom_id=%s FOR UPDATE',(self.cid,))
            await asyncio.wait_for(writer.execute("UPDATE files SET original_name='Concurrent update' WHERE file_id=%s",(self.file_id,)),3)
        finally:
            await writer.rollback()
            await deleter.rollback()
            await writer.close()
            await deleter.close()
