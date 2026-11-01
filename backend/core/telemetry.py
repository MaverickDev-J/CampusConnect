"""Bounded stage timings; no raw queries, prompts or private reasoning."""
from contextlib import contextmanager,asynccontextmanager
from contextvars import ContextVar
import json
import asyncio
import time
from uuid import uuid4

from sqlalchemy import text
from database.postgres import principal_session

current_trace=ContextVar('campus_trace',default=None)


class RunTrace:
    def __init__(self,*,trace_id=None,parent_run_id=None,resource_type=None,resource_id=None):
        self.run_id='run_'+uuid4().hex
        self.trace_id=trace_id or self.run_id
        self.parent_run_id=parent_run_id
        self.resource_type,self.resource_id=resource_type,resource_id
        self.outcome=None
        self.started=time.perf_counter()
        self.events=[]
        self.first_token_ms=None

    def first_token(self):
        if self.first_token_ms is None:
            self.first_token_ms=int((time.perf_counter()-self.started)*1000)


@contextmanager
def stage(name, **details):
    trace=current_trace.get()
    start=time.perf_counter()
    event={'stage':name,'offset_ms':int((start-trace.started)*1000) if trace else 0,
           'status':'success',**details}
    try:
        yield event
    except BaseException:
        event['status']='error'
        raise
    finally:
        event['duration_ms']=int((time.perf_counter()-start)*1000)
        if trace and len(trace.events)<100:
            trace.events.append(event)


async def save_trace(factory, principal, classroom_id, trace, state, status, *, kind='chat',origin='live'):
    try:
        async with asyncio.timeout(3):
            await _persist_trace(factory,principal,classroom_id,trace,state,status,kind=kind,origin=origin)
    except Exception:
        pass


async def _persist_trace(factory, principal, classroom_id, trace, state, status, *, kind='chat',origin='live'):
    if not classroom_id:
        return
    try:
        async with principal_session(factory,principal['user_id']) as session:
            await session.execute(text('''INSERT INTO ai_runs(run_id,actor_id,classroom_id,kind,origin,status,
              strategy,cache_status,fallback_reason,duration_ms,first_token_ms,source_ids,events,
              trace_id,parent_run_id,resource_type,resource_id)
              VALUES (:id,:actor,:classroom,:kind,:origin,:status,:strategy,:cache,:fallback,:duration,:first,
              CAST(:sources AS jsonb),CAST(:events AS jsonb),:trace,:parent,:resource_type,:resource)'''),
              {'id':trace.run_id,'actor':principal['user_id'],'classroom':classroom_id,'kind':kind,'origin':origin,
               'status':status,'strategy':state.get('retrieval_strategy'),'cache':state.get('cache_status','miss'),
               'fallback':state.get('rerank_fallback_reason') or state.get('routing_fallback_reason'),'duration':int((time.perf_counter()-trace.started)*1000),
               'first':trace.first_token_ms,'sources':json.dumps([s['chunk_id'] for s in state.get('used_sources',[])]),
               'events':json.dumps(trace.events),'trace':trace.trace_id,'parent':trace.parent_run_id,
               'resource_type':trace.resource_type,'resource':trace.resource_id})
    except Exception:
        # Operational telemetry is best effort; approval/action persistence isn't.
        pass


@asynccontextmanager
async def operation_trace(factory,principal,classroom_id,operation,*,kind,trace_id=None,parent_run_id=None,
                          resource_type=None,resource_id=None,join=False):
    parent=current_trace.get()
    if join and parent:
        with stage(operation):
            yield parent
        return
    trace=RunTrace(trace_id=trace_id or (parent.trace_id if parent else None),
        parent_run_id=parent_run_id or (parent.run_id if parent else None),
        resource_type=resource_type,resource_id=resource_id)
    token=current_trace.set(trace)
    outcome='success'
    try:
        with stage(operation):
            yield trace
    except (GeneratorExit,asyncio.CancelledError):
        outcome='cancelled'
        raise
    except Exception:
        outcome='error'
        raise
    finally:
        current_trace.reset(token)
        await save_trace(factory,principal,classroom_id,trace,{},trace.outcome or outcome,kind=kind)
