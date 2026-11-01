"""Student PDF chat regressions, with real authorization and controlled providers."""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

import psycopg

from api.agent.postgres_graph import PostgresRag
from core.gemini_budget import ProviderUnavailable
from tests import test_files_chat as file_helpers
from tests.test_files_chat import FakeEmbeddings,rag_route
from tests.test_postgres_api import PostgresApiFixture,running_app


class StudentChatRegressionTests(PostgresApiFixture):
    setup_course=file_helpers.FilesChatTests.setup_course
    upload=file_helpers.FilesChatTests.upload
    worker=file_helpers.FilesChatTests.worker

    async def test_query_and_retrieval_keys_reach_the_correct_clients(self):
        from postgres_main import create_app
        query=SimpleNamespace(aio=SimpleNamespace(aclose=AsyncMock()))
        retrieval=SimpleNamespace(aio=SimpleNamespace(aclose=AsyncMock()))
        def create(api_key):
            return {'query-key':query,'retrieval-key':retrieval}[api_key]
        with patch.dict(os.environ,{'GEMINI_CHAT_KEYS':'query-key','GEMINI_INGESTION_KEYS':'retrieval-key',
            'GEMINI_API_KEY':'stale-legacy-key'}),patch('postgres_main.genai.Client',side_effect=create) as constructor:
            app=create_app(self.runtime_url,storage_root=self.storage)
            async with running_app(app):
                self.assertIs(app.state.answer.client.client,query)
                self.assertIs(app.state.workflows.generator.client.client,query)
                self.assertIs(app.state.rag.embeddings.client.client,retrieval)
                self.assertIs(app.state.rag.reranker.client.client,retrieval)
                self.assertEqual(constructor.call_count,2)
        query.aio.aclose.assert_awaited_once()
        retrieval.aio.aclose.assert_awaited_once()

    async def prepared(self):
        await self.setup_course()
        self.file_id=(await self.upload()).json()['file_id']
        self.student,self.student_headers=await self.account('student')
        joined=await self.client.post('/api/classrooms/join',headers=self.student_headers,
            json={'join_code':self.classroom['join_code']})
        self.assertEqual(joined.status_code,200)
        self.app.state.rag=PostgresRag(self.app.state.accounts.factory,FakeEmbeddings(),route=rag_route)

    async def test_suggestions_follow_ready_evidence_membership_and_deletion(self):
        await self.prepared()
        params={'classroom_id':self.cid}
        pending=await self.client.get('/api/chat/quick-prompts',headers=self.student_headers,params=params)
        self.assertEqual(pending.json()['prompts'],[])
        await (await self.worker()).run_once()
        ready=await self.client.get('/api/chat/quick-prompts',headers=self.student_headers,params=params)
        self.assertEqual(ready.status_code,200,ready.text)
        prompts=ready.json()['prompts']
        self.assertEqual(len(prompts),4)
        self.assertTrue(all(prompt['file_id']==self.file_id and 'notes.pdf' in prompt['prompt'] for prompt in prompts))
        _,outsider=await self.account('outsider')
        self.assertEqual((await self.client.get('/api/chat/quick-prompts',headers=outsider,params=params)).status_code,403)
        # Another classroom must never inherit these suggestions.
        other=(await self.client.post('/api/classrooms',headers=self.headers,json={'name':'Other course'})).json()
        self.assertEqual((await self.client.get('/api/chat/quick-prompts',headers=self.headers,
            params={'classroom_id':other['classroom_id']})).json()['prompts'],[])
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('DELETE FROM classroom_members WHERE classroom_id=%s AND user_id=%s',
                (self.cid,self.student['user_id']))
        self.assertEqual((await self.client.get('/api/chat/quick-prompts',headers=self.student_headers,params=params)).status_code,403)
        await self.client.delete('/api/files/'+self.file_id,headers=self.headers)
        self.assertEqual((await self.client.get('/api/chat/quick-prompts',headers=self.headers,params=params)).json()['prompts'],[])

    async def test_router_timeout_still_retrieves_and_answers_student_pdf(self):
        await self.prepared()
        await (await self.worker()).run_once()
        cancelled=asyncio.Event()
        async def stuck_router(state):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.app.state.rag=PostgresRag(self.app.state.accounts.factory,FakeEmbeddings(),route=stuck_router,route_timeout=0.01)
        async def answer(state):
            self.assertEqual(state['used_sources'][0]['file_id'],self.file_id)
            self.assertIn('backpropagation',state['retrieved_chunks'][0].text)
            yield 'An answer based on the student-accessible PDF.'
        self.app.state.answer=answer
        session=(await self.client.post('/api/chat/sessions',headers=self.student_headers,
            json={'classroom_id':self.cid,'file_id':self.file_id})).json()
        result=await self.client.post('/api/chat/sessions/'+session['session_id']+'/message',
            headers=self.student_headers,json={'query':'Explain backpropagation.'})
        events=[json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
        self.assertTrue(cancelled.is_set())
        self.assertNotIn('error',[event['t'] for event in events])
        self.assertEqual(next(event['d'] for event in events if event['t']=='sources')[0]['file_id'],self.file_id)
        history=(await self.client.get('/api/chat/sessions/'+session['session_id']+'/history',headers=self.student_headers)).json()
        self.assertEqual(history['count'],2)
        with psycopg.connect(self.owner_url) as conn:
            trace=conn.execute('SELECT status,fallback_reason FROM ai_runs WHERE actor_id=%s',
                (self.student['user_id'],)).fetchone()
        self.assertEqual(trace,('success','routing_timeout'))

    async def test_provider_failure_is_actionable_and_does_not_save_a_false_answer(self):
        await self.prepared()
        await (await self.worker()).run_once()
        async def unavailable(state):
            raise ProviderUnavailable(503)
            yield
        self.app.state.answer=unavailable
        session=(await self.client.post('/api/chat/sessions',headers=self.student_headers,json={'classroom_id':self.cid})).json()
        result=await self.client.post('/api/chat/sessions/'+session['session_id']+'/message',
            headers=self.student_headers,json={'query':'Explain backpropagation.'})
        self.assertIn('The AI service is temporarily unavailable',result.text)
        self.assertNotIn('"t": "sources"',result.text)
        history=(await self.client.get('/api/chat/sessions/'+session['session_id']+'/history',headers=self.student_headers)).json()
        self.assertEqual(history['count'],0)
