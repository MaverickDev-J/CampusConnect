"""Groq transport, total-token accounting and bounded RAG regressions."""
import asyncio
from contextlib import aclosing
import os
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock,patch

import psycopg

from core.groq_llm import GroqLLM,MODEL
from core.gemini_budget import BudgetExhausted,ProjectBudget,ProviderUnavailable
from api.agent.groq_nodes import GroqAnswer,GroqReranker
from api.agent.state import RetrievedChunk,ChatMessage
from api.services.retrieval.ranking import Candidate
from tests.test_postgres_api import PostgresApiFixture,running_app


def fake_llm(create):
    budget=NS(reserve=AsyncMock(return_value='reservation'),finish=AsyncMock())
    return GroqLLM(NS(chat=NS(completions=NS(create=create))),budget),budget


class Stream:
    def __init__(self,parts):self.parts,self.closed=parts,False
    async def close(self):self.closed=True
    async def chunks(self):
        for part in self.parts:yield part
    def __aiter__(self):return self.chunks()


class GroqTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_response_and_unknown_usage_preserved(self):
        create=AsyncMock(return_value=NS(choices=[NS(finish_reason='stop',message=NS(content='{"intent":"RAG_SEARCH"}'))],usage=None))
        llm,budget=fake_llm(create)
        response=await llm.generate('system','question',workload='route',schema={'type':'object'},max_output=256)
        self.assertIsNone(response.input_tokens)
        request=create.call_args.kwargs
        self.assertEqual(request['model'],MODEL)
        self.assertTrue(request['response_format']['json_schema']['strict'])
        self.assertFalse(request['include_reasoning'])
        self.assertGreater(budget.reserve.call_args.args[2],llm.count([]))
        self.assertEqual(budget.reserve.call_args.args[3],256)
        self.assertEqual(budget.finish.call_args.args[1],'success')

    async def test_stream_filters_reasoning_records_groq_usage_and_closes(self):
        parts=[NS(choices=[NS(delta=NS(content=None,reasoning='PRIVATE_REASONING'),finish_reason=None)],usage=None),
            NS(choices=[NS(delta=NS(content='Visible answer'),finish_reason='stop')],usage=None),
            NS(choices=[],usage=None,x_groq=NS(usage=NS(prompt_tokens=100,completion_tokens=50,completion_tokens_details=NS(reasoning_tokens=30))))]
        stream=Stream(parts)
        llm,budget=fake_llm(AsyncMock(return_value=stream))
        result=''.join([text async for text in llm.stream('system','question')])
        self.assertEqual(result,'Visible answer')
        self.assertTrue(stream.closed)
        self.assertEqual(budget.finish.call_args.args[1:3],('success',(100,50,30)))

    async def test_disconnect_stays_charged_and_never_retries(self):
        stream=Stream([NS(choices=[NS(delta=NS(content='Partial'),finish_reason=None)],usage=None)])
        create=AsyncMock(return_value=stream)
        llm,budget=fake_llm(create)
        response=llm.stream('system','question')
        self.assertEqual(await anext(response),'Partial')
        await response.aclose()
        self.assertTrue(stream.closed)
        self.assertEqual(budget.finish.call_args.args[1],'cancelled')
        create.assert_awaited_once()

    async def test_429_honors_retry_after_and_masks_provider_payload(self):
        class Limited(RuntimeError):
            status_code=429
            response=NS(headers={'retry-after':'90'})
        create=AsyncMock(side_effect=Limited('private key or document content'))
        llm,budget=fake_llm(create)
        with self.assertRaises(ProviderUnavailable) as error:
            await llm.generate('system','question',workload='rerank')
        self.assertEqual(error.exception.status,429)
        self.assertNotIn('private',str(error.exception))
        self.assertGreaterEqual(budget.finish.call_args.kwargs['cooldown'],90)
        create.assert_awaited_once()

    async def test_optional_503_does_not_block_answer_and_denial_never_calls_sdk(self):
        class Unavailable(RuntimeError):status_code=503
        create=AsyncMock(side_effect=Unavailable())
        llm,budget=fake_llm(create)
        with self.assertRaises(ProviderUnavailable):
            await llm.generate('system','question',workload='rerank')
        self.assertEqual(budget.finish.call_args.kwargs['cooldown'],0)
        budget.reserve.side_effect=BudgetExhausted('token_limit')
        create.reset_mock()
        with self.assertRaises(BudgetExhausted):
            await llm.generate('system','question',workload='answer')
        create.assert_not_called()

    async def test_reranking_validates_ids_and_preserves_unranked_tail(self):
        llm,_=fake_llm(AsyncMock())
        llm.generate=AsyncMock(return_value=NS(text='{"ranked_ids":["p5","p4","p3","p2","p1","p0"]}',input_tokens=50,output_tokens=30))
        candidates=[Candidate(str(i),'document evidence '*100) for i in range(9)]
        result=await GroqReranker(llm).rerank('question',candidates)
        self.assertEqual([c.chunk_id for c in result.candidates],['5','4','3','2','1','0','6','7','8'])
        llm.generate.return_value.text='{"ranked_ids":["forged"]}'
        fallback=await GroqReranker(llm).rerank('question',candidates)
        self.assertEqual(fallback.candidates,candidates)
        self.assertEqual(fallback.fallback_reason,'invalid_ranking')

    def test_answer_bounds_real_context_without_losing_question_or_mutating_sources(self):
        llm,_=fake_llm(AsyncMock())
        chunks=[RetrievedChunk(text='network evidence '*2000,source_file='lecture.pdf',file_type='pdf',page_number=i) for i in range(1,7)]
        state={'query':'Explain TCP reliability.','retrieved_chunks':chunks,'chat_history':[ChatMessage(role='user',content='history '*1000)],
               'classroom_context':{'name':'Networking','subject':'Networks'}}
        prompt=GroqAnswer(llm).prompt(state)
        self.assertIn(state['query'],prompt)
        self.assertIn('lecture.pdf',prompt)
        self.assertGreater(len(chunks[0].text),10000)
        self.assertLess(llm.count([{'content':prompt}]),2800)


class GroqBudgetTests(PostgresApiFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.project='groq-test-'+self.tag
        self.budget=ProjectBudget(self.app.state.accounts.factory,self.project)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('''INSERT INTO ai_budget_policies(project_key,model,rpm,input_tpm,rpd,concurrent_requests,
              reserve_rpm,reserve_tpm,reserve_rpd,reserve_slots,token_accounting,tokens_per_day,reserve_tpd,rolling_day)
              SELECT %s,model,20,7000,600,2,2,4500,100,1,'total',160000,20000,true
              FROM ai_budget_policies WHERE project_key='groq-default' AND model=%s''',(self.project,MODEL))

    async def asyncTearDown(self):
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('DELETE FROM ai_budget_calls WHERE project_key=%s',(self.project,))
            conn.execute('DELETE FROM ai_budget_policies WHERE project_key=%s',(self.project,))
        await super().asyncTearDown()

    async def test_output_reservations_keep_answer_headroom(self):
        first=await self.budget.reserve(MODEL,'rerank',1500,512)
        await self.budget.finish(first,'success',(500,100,None))
        with self.assertRaises(BudgetExhausted) as denied:
            await self.budget.reserve(MODEL,'route',500,256)
        self.assertEqual(denied.exception.reason,'token_limit')
        answer=await self.budget.reserve(MODEL,'answer',2700,1536)
        self.assertTrue(answer)

    async def test_app_uses_groq_for_all_text_and_gemini_for_embeddings(self):
        from postgres_main import create_app
        google=NS(aio=NS(aclose=AsyncMock()))
        groq=NS(close=AsyncMock())
        with patch.dict(os.environ,{'AI_TEXT_PROVIDER':'groq','GROQ_API_KEY':'groq-test-key',
            'GEMINI_INGESTION_KEYS':'embedding-test-key','GEMINI_CHAT_KEYS':'unused-chat-key'}), \
            patch('postgres_main.genai.Client',return_value=google) as google_factory, \
            patch('postgres_main.AsyncGroq',return_value=groq) as groq_factory:
            app=create_app(self.runtime_url,storage_root=self.storage)
            async with running_app(app):
                self.assertEqual(app.state.text_provider,'groq')
                self.assertIs(app.state.rag.embeddings.client.client,google)
                self.assertIs(app.state.answer.llm.client,groq)
                self.assertIs(app.state.rag.reranker.llm,app.state.answer.llm)
                self.assertIs(app.state.workflows.generator.llm,app.state.answer.llm)
                self.assertIn('groq:',app.state.answer_cache.config_version)
                google_factory.assert_called_once_with(api_key='embedding-test-key')
                self.assertEqual(groq_factory.call_args.kwargs['max_retries'],0)
        google.aio.aclose.assert_awaited_once()
        groq.close.assert_awaited_once()

    async def test_actual_total_and_rolling_day_ignore_quota_day_labels(self):
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('UPDATE ai_budget_policies SET tokens_per_day=2000,reserve_tpd=0,reserve_tpm=0 WHERE project_key=%s',(self.project,))
        call=await self.budget.reserve(MODEL,'answer',100,200)
        await self.budget.finish(call,'success',(450,600,100))
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE ai_budget_calls SET created_at=now()-interval '61 seconds',quota_day=quota_day-1 WHERE project_key=%s",(self.project,))
        with self.assertRaises(BudgetExhausted) as denied:
            await self.budget.reserve(MODEL,'answer',1000,50)
        self.assertEqual(denied.exception.reason,'daily_token_limit')
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE ai_budget_calls SET created_at=now()-interval '25 hours' WHERE project_key=%s",(self.project,))
        self.assertTrue(await self.budget.reserve(MODEL,'answer',1000,50))
