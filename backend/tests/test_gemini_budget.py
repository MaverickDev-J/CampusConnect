"""Shared budget races, provider failures, streaming cancellation and isolation."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import psycopg
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from core.gemini_budget import BudgetExhausted, BudgetedGemini, ProjectBudget, ProviderUnavailable, budget_scope
from core.llm_router import call_gemini_with_fallback
from api.services.retrieval.ranking import Candidate, GeminiReranker
from tests.test_postgres_api import PostgresApiFixture


class GeminiBudgetTests(PostgresApiFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.project = 'budget-test-' + self.tag
        self.model = 'gemini-3.8-flash'
        self.budget = ProjectBudget(self.app.state.accounts.factory, self.project)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('''INSERT INTO ai_budget_policies VALUES
              (%s,%s,10,100000,100,10,1,1000,1,1,NULL)''', (self.project,self.model))

    async def asyncTearDown(self):
        try:
            with psycopg.connect(self.owner_url) as conn:
                conn.execute('DELETE FROM ai_budget_calls WHERE project_key=%s', (self.project,))
                conn.execute('DELETE FROM ai_budget_policies WHERE project_key=%s', (self.project,))
        finally:
            await super().asyncTearDown()

    def policy(self, **changes):
        allowed = {'rpm','input_tpm','rpd','concurrent_requests','reserve_rpm','reserve_tpm','reserve_rpd','reserve_slots'}
        self.assertFalse(set(changes)-allowed)
        with psycopg.connect(self.owner_url) as conn:
            for key,value in changes.items():
                conn.execute(f'UPDATE ai_budget_policies SET {key}=%s WHERE project_key=%s AND model=%s', (value,self.project,self.model))

    def calls(self):
        with psycopg.connect(self.owner_url, row_factory=psycopg.rows.dict_row) as conn:
            return conn.execute('SELECT * FROM ai_budget_calls WHERE project_key=%s ORDER BY created_at', (self.project,)).fetchall()

    async def test_shared_admission_race_keeps_answer_headroom_and_survives_restart(self):
        self.policy(rpm=5)
        async def attempt():
            try:
                # Separate service instances simulate independent API/worker containers.
                return await ProjectBudget(self.app.state.accounts.factory,self.project).reserve(self.model,'rerank',100,100)
            except BudgetExhausted:
                return None
        admitted = [value for value in await asyncio.gather(*(attempt() for _ in range(20))) if value]
        self.assertEqual(len(admitted), 4)
        await self.budget.reserve(self.model,'answer',100,100)
        with self.assertRaises(BudgetExhausted) as denied:
            await ProjectBudget(self.app.state.accounts.factory,self.project).reserve(self.model,'answer',100,100)
        self.assertEqual(denied.exception.reason,'request_limit')
        self.assertEqual(len(self.calls()),5)

    async def test_tokens_daily_limit_and_expired_leases(self):
        self.policy(concurrent_requests=2)
        call_id = await self.budget.reserve(self.model,'draft',100,100)
        with self.assertRaises(BudgetExhausted) as denied:
            await self.budget.reserve(self.model,'rerank',100,100)
        self.assertEqual(denied.exception.reason,'concurrency_limit')
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE ai_budget_calls SET lease_until=now()-interval '1 second' WHERE project_key=%s",(self.project,))
        await self.budget.reserve(self.model,'draft',100,100)
        await self.budget.finish(call_id,'error')
        self.policy(input_tpm=2000,reserve_tpm=1000)
        with self.assertRaises(BudgetExhausted) as denied:
            await self.budget.reserve(self.model,'rerank',1000,100)
        self.assertEqual(denied.exception.reason,'token_limit')
        # Quota-day accounting follows the provider's Pacific reset, not UTC.
        with psycopg.connect(self.owner_url) as conn:
            day = conn.execute("SELECT (clock_timestamp() AT TIME ZONE 'America/Los_Angeles')::date").fetchone()[0]
            self.assertTrue(all(call['quota_day']==day for call in self.calls()))
        self.policy(rpd=2)
        with self.assertRaises(BudgetExhausted) as denied:
            await self.budget.reserve(self.model,'answer',100,100)
        self.assertEqual(denied.exception.reason,'daily_limit')

    async def test_rolling_window_counts_both_sides_of_minute_boundary(self):
        self.policy(rpm=2,reserve_rpm=0)
        for _ in range(2):
            call_id = await self.budget.reserve(self.model,'answer',100,100)
            await self.budget.finish(call_id,'success')
        with self.assertRaises(BudgetExhausted):
            await self.budget.reserve(self.model,'answer',100,100)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE ai_budget_calls SET created_at=now()-interval '61 seconds' WHERE project_key=%s",(self.project,))
        await self.budget.reserve(self.model,'answer',100,100)

    async def test_unknown_model_and_unavailable_accounting_never_call_provider(self):
        generate = AsyncMock()
        raw = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        with self.assertRaises(BudgetExhausted):
            await BudgetedGemini(raw,self.budget,'answer').aio.models.generate_content(model='unconfigured',contents='hello')
        broken = ProjectBudget(lambda: (_ for _ in ()).throw(RuntimeError('Database unavailable')),self.project)
        with self.assertRaises(BudgetExhausted) as denied:
            await BudgetedGemini(raw,broken,'answer').aio.models.generate_content(model=self.model,contents='hello')
        self.assertEqual(denied.exception.reason,'budget_unavailable')
        generate.assert_not_called()

    async def test_429_is_single_attempt_shared_cooldown_and_rerank_fallback(self):
        class RateLimited(RuntimeError):
            code = 429
            response = SimpleNamespace(headers={'retry-after':'120'})
        generate = AsyncMock(side_effect=RateLimited('sensitive provider payload'))
        raw = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        pool = SimpleNamespace(has_keys=True,get_client=lambda:(raw,'fake-key'),pool_name='test')
        with self.assertRaises(ProviderUnavailable) as failed:
            with budget_scope(self.budget,'route'):
                await call_gemini_with_fallback(model_chain=[self.model,'unconfigured'],contents='hi',key_pool=pool)
        self.assertNotIn('sensitive',str(failed.exception))
        generate.assert_awaited_once()
        self.assertEqual(generate.call_args.kwargs['config'].http_options.retry_options.attempts,1)
        reranker = GeminiReranker(BudgetedGemini(raw,self.budget,'rerank'))
        result = await reranker.rerank('query',[Candidate('a','first'),Candidate('b','second')])
        self.assertEqual(result.fallback_reason,'budget_exhausted')
        self.assertEqual(generate.await_count,1)
        with self.assertRaises(BudgetExhausted) as denied:
            await ProjectBudget(self.app.state.accounts.factory,self.project).reserve(self.model,'answer',10,10)
        self.assertEqual(denied.exception.reason,'provider_cooldown')
        self.assertGreaterEqual(denied.exception.retry_after,119)
        self.assertEqual(self.calls()[0]['provider_status'],429)

    async def test_success_records_observed_usage_without_storing_content(self):
        response = SimpleNamespace(text='answer',usage_metadata=SimpleNamespace(prompt_token_count=17,candidates_token_count=6,thoughts_token_count=4))
        generate = AsyncMock(return_value=response)
        raw = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        await BudgetedGemini(raw,self.budget,'answer').aio.models.generate_content(model=self.model,contents='private question')
        row = self.calls()[0]
        self.assertEqual((row['actual_input'],row['actual_output'],row['actual_thinking']),(17,6,4))
        self.assertEqual(row['outcome'],'success')
        self.assertNotIn('private question',str(row))
        self.assertGreater(row['reserved_input'],17)

    async def test_stream_partial_failure_and_client_close_release_capacity(self):
        async def partial():
            yield SimpleNamespace(text='partial',usage_metadata=None)
            raise RuntimeError('sensitive failure')
        generate = AsyncMock(side_effect=lambda **kwargs:partial())
        raw = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate)))
        wrapped = BudgetedGemini(raw,self.budget,'answer')
        stream = await wrapped.aio.models.generate_content_stream(model=self.model,contents='question')
        self.assertEqual((await anext(stream)).text,'partial')
        with self.assertRaises(ProviderUnavailable):
            await anext(stream)
        self.assertEqual(self.calls()[0]['outcome'],'error')
        stream = await wrapped.aio.models.generate_content_stream(model=self.model,contents='another question')
        await anext(stream)
        await stream.aclose()
        self.assertEqual(self.calls()[1]['outcome'],'cancelled')
        self.assertEqual(generate.await_count,2)
        async def complete():
            yield SimpleNamespace(text='complete',usage_metadata=SimpleNamespace(prompt_token_count=9,candidates_token_count=3,thoughts_token_count=2))
        generate.side_effect = lambda **kwargs:complete()
        stream = await wrapped.aio.models.generate_content_stream(model=self.model,contents='final question')
        self.assertEqual([part.text async for part in stream],['complete'])
        final = self.calls()[2]
        self.assertEqual((final['actual_input'],final['actual_output'],final['actual_thinking']),(9,3,2))
        self.assertEqual(final['outcome'],'success')

    async def test_task_cancellation_preserves_request_charge_and_releases_slot(self):
        started = asyncio.Event()
        async def wait(**kwargs):
            started.set()
            await asyncio.Event().wait()
        raw = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=wait)))
        task = asyncio.create_task(BudgetedGemini(raw,self.budget,'answer').aio.models.generate_content(model=self.model,contents='question'))
        await asyncio.wait_for(started.wait(),5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(self.calls()[0]['outcome'],'cancelled')
        self.assertIsNotNone(self.calls()[0]['finished_at'])

    async def test_runtime_cannot_read_usage_or_change_policies(self):
        for statement in ('SELECT * FROM ai_budget_calls','SELECT * FROM ai_budget_policies',
                          'UPDATE ai_budget_policies SET rpm=999999'):
            with self.assertRaises(ProgrammingError):
                async with self.app.state.accounts.factory() as session:
                    await session.execute(text(statement))
