"""Cross-process admission control. No prompts, credentials or user IDs are stored."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from types import SimpleNamespace
from uuid import uuid4

from google.genai import types
from sqlalchemy import text


class BudgetExhausted(RuntimeError):
    def __init__(self, reason, retry_after=60):
        super().__init__('AI capacity is temporarily unavailable')
        self.reason, self.retry_after = reason, retry_after


class ProviderUnavailable(RuntimeError):
    def __init__(self, status=None, retry_after=60):
        super().__init__('AI provider is temporarily unavailable')
        self.status = status
        self.retry_after = retry_after


active_budget = ContextVar('campus_gemini_budget', default=None)


@contextmanager
def budget_scope(budget, workload, *, input_tokens=None):
    token = active_budget.set((budget, workload, input_tokens) if budget else None)
    try:
        yield
    finally:
        active_budget.reset(token)


def _json_value(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json', exclude_none=True)
    raise TypeError('Unsupported provider input')


def estimate_input(contents, config):
    # Conservative text reservation, not an exact tokenizer or a billing quote.
    # Multimodal calls use the provider count endpoint before generation.
    return len(json.dumps([contents, config], default=_json_value, ensure_ascii=False).encode('utf-8')) + 256


def _usage(response):
    usage = getattr(response, 'usage_metadata', None)
    def count(name):
        value = getattr(usage, name, None)
        return value if isinstance(value, int) and value >= 0 else None
    return count('prompt_token_count'), count('candidates_token_count'), count('thoughts_token_count')


def _failure(error):
    status = getattr(error, 'code', None)
    status = status if isinstance(status, int) else None
    cooldown = 60 if status == 429 else 15 if status in (500,502,503,504) else 0
    headers = getattr(getattr(error, 'response', None), 'headers', {}) or {}
    retry = headers.get('retry-after')
    if status in (429,503) and retry:
        try:
            seconds = float(retry)
        except (ValueError, TypeError):
            try:
                seconds = (parsedate_to_datetime(retry)-datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = 0
        if math.isfinite(seconds):
            cooldown = max(cooldown, min(86400, max(0, int(seconds)+1)))
    return status, cooldown


class ProjectBudget:
    def __init__(self, factory, project=None):
        self.factory = factory
        self.project = project or os.getenv('GEMINI_BUDGET_PROJECT', 'campusconnect-default')
        if not self.project or len(self.project)>200:
            raise ValueError('Invalid Gemini budget project')

    async def reserve(self, model, workload, input_tokens, output_tokens):
        call_id = uuid4().hex
        try:
            async with self.factory() as session, session.begin():
                await session.execute(text("SET LOCAL lock_timeout='2s'"))
                await session.execute(text("SET LOCAL statement_timeout='3s'"))
                row = (await session.execute(text('''SELECT * FROM public.reserve_ai_call(CAST(:id AS uuid),
                  :project,:model,:work,:input,:output)'''), {'id': call_id, 'project': self.project,
                  'model': model.removeprefix('models/'), 'work': workload, 'input': input_tokens, 'output': output_tokens})).mappings().one()
        except Exception:
            raise BudgetExhausted('budget_unavailable', 5) from None
        if not row['allowed']:
            raise BudgetExhausted(row['reason'], row['retry_after'])
        return call_id

    async def finish(self, call_id, outcome, usage=(None,None,None), *, status=None, cooldown=0):
        try:
            async with asyncio.timeout(4):
                async with self.factory() as session, session.begin():
                    await session.execute(text("SET LOCAL lock_timeout='2s'"))
                    await session.execute(text("SET LOCAL statement_timeout='3s'"))
                    await session.execute(text('''SELECT public.finish_ai_call(CAST(:id AS uuid),:outcome,
                      :input,:output,:thinking,:status,:cooldown)'''), {'id': call_id, 'outcome': outcome,
                      'input': usage[0], 'output': usage[1], 'thinking': usage[2], 'status': status, 'cooldown': cooldown})
        except Exception:
            # Never repeat a completed provider call because accounting failed.
            # Its reservation remains charged and its concurrency lease expires.
            return False
        return True


class BudgetedGemini:
    """Minimal SDK-compatible async model surface for PostgreSQL application paths."""
    def __init__(self, client, budget, workload, *, input_tokens=None):
        self.client, self.budget, self.workload, self.input_tokens = client, budget, workload, input_tokens
        self.aio = SimpleNamespace(models=self)

    def _config(self, config, kind):
        config = config or (types.EmbedContentConfig() if kind=='embed_content' else
                            types.CountTokensConfig() if kind=='count_tokens' else types.GenerateContentConfig())
        changes = {'http_options': types.HttpOptions(timeout=120000, retry_options=types.HttpRetryOptions(attempts=1))}
        if kind.startswith('generate'):
            limit = {'route':256,'rerank':1024,'draft':2048,'answer':4096,'extract':8192}[self.workload]
            changes['max_output_tokens'] = min(config.max_output_tokens or limit, limit)
        return config.model_copy(update=changes)

    async def _call(self, kind, model, contents, config):
        config = self._config(config, kind)
        work = 'count' if kind=='count_tokens' else self.workload
        estimate = 0 if work=='count' else self.input_tokens if self.input_tokens is not None else estimate_input(contents, config)
        call_id = await self.budget.reserve(model, work, estimate, getattr(config,'max_output_tokens',0) or 0)
        usage, outcome, status, cooldown = (None,None,None), 'error', None, 0
        try:
            async with asyncio.timeout(120):
                result = await getattr(self.client.aio.models, kind)(model=model, contents=contents, config=config)
                usage = _usage(result)
                outcome = 'success'
                return result
        except asyncio.CancelledError:
            outcome = 'cancelled'
            raise
        except Exception as exc:
            status, cooldown = _failure(exc)
            raise ProviderUnavailable(status, cooldown or 60) from None
        finally:
            await self.budget.finish(call_id, outcome, usage, status=status, cooldown=cooldown)

    async def generate_content(self, *, model, contents, config=None):
        return await self._call('generate_content', model, contents, config)

    async def embed_content(self, *, model, contents, config=None):
        return await self._call('embed_content', model, contents, config)

    async def count_tokens(self, *, model, contents, config=None):
        return await self._call('count_tokens', model, contents, config)

    async def generate_content_stream(self, *, model, contents, config=None):
        # The SDK returns an async iterator from an awaited coroutine.
        config = self._config(config, 'generate_content_stream')
        async def events():
            call_id = await self.budget.reserve(model, self.workload, estimate_input(contents, config), config.max_output_tokens)
            usage, outcome, status, cooldown = (None,None,None), 'error', None, 0
            stream = None
            try:
                async with asyncio.timeout(120):
                    stream = await self.client.aio.models.generate_content_stream(model=model, contents=contents, config=config)
                    async for part in stream:
                        observed = _usage(part)
                        usage = tuple(new if new is not None else old for new,old in zip(observed,usage))
                        yield part
                    outcome = 'success'
            except (asyncio.CancelledError, GeneratorExit):
                outcome = 'cancelled'
                raise
            except Exception as exc:
                status, cooldown = _failure(exc)
                raise ProviderUnavailable(status, cooldown or 60) from None
            finally:
                if stream is not None and hasattr(stream,'aclose'):
                    try:
                        async with asyncio.timeout(2):
                            await stream.aclose()
                    except Exception:
                        pass
                await self.budget.finish(call_id, outcome, usage, status=status, cooldown=cooldown)
        return events()
