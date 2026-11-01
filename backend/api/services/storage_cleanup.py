"""Delete only queued application files within the configured storage root."""
import asyncio
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from core.telemetry import operation_trace


class StorageCleanup:
    def __init__(self, factory, storage_root, *, persist=None):
        self.factory, self.root = factory, Path(storage_root).resolve()
        self.persist = persist

    async def run_once(self):
        token = uuid4().hex
        async with self.factory() as session, session.begin():
            job = (await session.execute(text('SELECT * FROM public.claim_storage_cleanup(:token)'), {'token':token})).mappings().first()
        if not job:
            return False
        async with operation_trace(self.factory,{'user_id':job['actor_id']},job.get('classroom_id'),
                'storage.cleanup',kind='cleanup',trace_id=job.get('trace_id'),parent_run_id=job.get('parent_run_id'),
                resource_type='file',resource_id=job['file_id']) as trace:
            if not await self._cleanup(job,token):trace.outcome='error'
        return True

    async def _cleanup(self,job,token):
        success = False
        try:
            path = Path(job['storage_path'])
            resolved = path.resolve()
            if resolved == self.root or not resolved.is_relative_to(self.root) or path.is_symlink():
                raise ValueError('Unsafe cleanup path')
            async with self.factory() as session:
                in_use = (await session.execute(text('SELECT public.cleanup_path_in_use(:path)'), {'path':job['storage_path']})).scalar_one()
            if in_use:
                raise ValueError('Path is still referenced')
            # A missing file is success after a crash between unlink and DB ack.
            # This is a single-file operation, never recursive directory removal.
            await asyncio.to_thread(resolved.unlink, missing_ok=True)
            if self.persist:
                await self.persist()
            success = True
        except Exception:
            pass
        async with self.factory() as session, session.begin():
            await session.execute(text('SELECT public.finish_storage_cleanup(:id,:token,:success)'),
              {'id':job['file_id'], 'token':token, 'success':success})
        return success
