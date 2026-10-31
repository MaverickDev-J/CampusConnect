"""Delete only queued application files within the configured storage root."""
import asyncio
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text


class StorageCleanup:
    def __init__(self, factory, storage_root):
        self.factory, self.root = factory, Path(storage_root).resolve()

    async def run_once(self):
        token = uuid4().hex
        async with self.factory() as session, session.begin():
            job = (await session.execute(text('SELECT * FROM public.claim_storage_cleanup(:token)'), {'token':token})).mappings().first()
        if not job:
            return False
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
            success = True
        except Exception:
            pass
        async with self.factory() as session, session.begin():
            await session.execute(text('SELECT public.finish_storage_cleanup(:id,:token,:success)'),
              {'id':job['file_id'], 'token':token, 'success':success})
        return True
