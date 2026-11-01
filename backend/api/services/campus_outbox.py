"""At-least-once event delivery; leases prevent concurrent duplicate claims."""
import asyncio
from uuid import uuid4
from sqlalchemy import text
from core.telemetry import operation_trace


class CampusOutbox:
    def __init__(self, factory, publish):
        self.factory, self.publish = factory, publish

    async def run_once(self):
        token = uuid4().hex
        async with self.factory() as session, session.begin():
            row = (await session.execute(text('SELECT * FROM public.claim_campus_event(:token)'), {'token': token})).mappings().first()
        if not row:
            return False
        async with operation_trace(self.factory,{'user_id':row['actor_id']},row['classroom_id'],
                'outbox.deliver',kind='delivery',trace_id=row.get('trace_id'),parent_run_id=row.get('parent_run_id'),
                resource_type='event',resource_id=row['event_id']) as trace:
            success=await self._deliver(row,token)
            if not success:trace.outcome='error'
        return True

    async def _deliver(self,row,token):
        success = False
        try:
            await asyncio.wait_for(self.publish(row['classroom_id'] or 'global_events',
                {'type': row['event_type'], 'event_id': row['event_id']}), timeout=10)
            success = True
        except Exception:
            pass
        async with self.factory() as session, session.begin():
            await session.execute(text('SELECT public.finish_campus_event(:id,:token,:success)'),
                {'id': row['event_id'], 'token': token, 'success': success})
        return success
