"""Scoped file metadata and atomic upload/job registration."""
from fastapi import HTTPException
from sqlalchemy import text
from database.postgres import principal_session
from core.telemetry import current_trace


class PostgresFiles:
    def __init__(self, factory):
        self.factory = factory

    async def authorize(self, principal, classroom_id, *, write=False):
        async with principal_session(self.factory, principal["user_id"]) as session:
            await self.authorize_in_session(session, classroom_id, write=write)

    async def authorize_in_session(self, session, classroom_id, *, write=False):
        allowed = (await session.execute(text(
            "SELECT public.can_write_classroom(:id)" if write else "SELECT public.can_read_classroom(:id)"
        ), {"id": classroom_id})).scalar_one()
        if not allowed:
            raise HTTPException(403, "Classroom access denied")

    async def register(self, principal, document):
        async with principal_session(self.factory, principal["user_id"]) as session:
            inserted = (await session.execute(text("""INSERT INTO files
              (file_id,classroom_id,original_name,storage_path,file_type,sha256_hash,uploaded_by,mime_type,file_size_bytes,doc_type)
              VALUES (:file_id,:classroom_id,:original_name,:storage_path,:file_type,:sha256_hash,:uploaded_by,:mime_type,:file_size_bytes,:doc_type)
              ON CONFLICT(classroom_id,sha256_hash) DO NOTHING RETURNING file_id"""), document)).scalar_one_or_none()
            if inserted:
                trace=current_trace.get()
                await session.execute(text("INSERT INTO ingestion_jobs(file_id,actor_id,trace_id,parent_run_id) VALUES (:id,:actor,:trace,:parent)"),
                    {'id':inserted,'actor':principal['user_id'],'trace':trace.trace_id if trace else None,'parent':trace.run_id if trace else None})
                return inserted, True
            existing = (await session.execute(text("SELECT file_id,status FROM files WHERE classroom_id=:classroom_id AND sha256_hash=:sha256_hash"), document)).mappings().one()
            if existing["status"] == "deleted":
                raise HTTPException(409, "This file was deleted; restoration requires a new document revision")
            if existing["status"] == "failed":
                await session.execute(text("SELECT public.retry_ingestion_job(:id)"), {"id": existing["file_id"]})
            return existing["file_id"], False

    async def get(self, principal, file_id):
        async with principal_session(self.factory, principal["user_id"]) as session:
            row = (await session.execute(text("""SELECT f.*,
              (SELECT count(*) FROM chunks c WHERE c.file_id=f.file_id AND c.revision=f.active_revision) AS chunk_count,
              (SELECT j.state FROM ingestion_jobs j WHERE j.file_id=f.file_id) AS job_state
              FROM files f WHERE f.file_id=:id AND f.status<>'deleted'"""), {"id": file_id})).mappings().first()
            if not row:
                raise HTTPException(404, "File not found")
            return dict(row)

    async def list(self, principal, classroom_id, page, limit, doc_type=None, file_type=None):
        await self.authorize(principal, classroom_id)
        async with principal_session(self.factory, principal["user_id"]) as session:
            params = {"id": classroom_id, "doc_type": doc_type, "file_type": file_type, "limit": limit, "skip": (page-1)*limit}
            clause = """FROM files WHERE classroom_id=:id AND status<>'deleted'
              AND (CAST(:doc_type AS text) IS NULL OR doc_type=:doc_type)
              AND (CAST(:file_type AS text) IS NULL OR file_type=:file_type)"""
            total = (await session.execute(text("SELECT count(*) " + clause), params)).scalar_one()
            rows = (await session.execute(text("""SELECT files.*,
              (SELECT count(*) FROM chunks c WHERE c.file_id=files.file_id AND c.revision=files.active_revision) AS chunk_count,
              (SELECT j.state FROM ingestion_jobs j WHERE j.file_id=files.file_id) AS job_state
              """ + clause + " ORDER BY uploaded_at DESC,file_id LIMIT :limit OFFSET :skip"), params)).mappings().all()
        return [dict(row) for row in rows], total

    async def retry(self, principal, file_id):
        document = await self.get(principal, file_id)
        await self.authorize(principal, document["classroom_id"], write=True)
        async with principal_session(self.factory, principal["user_id"]) as session:
            await session.execute(text("SELECT public.retry_ingestion_job(:id)"), {"id": file_id})

    async def delete(self, principal, file_id):
        document = await self.get(principal, file_id)
        await self.authorize(principal, document['classroom_id'], write=True)
        async with principal_session(self.factory, principal['user_id']) as session:
            await session.execute(text('SELECT public.queue_file_cleanup(:id)'), {'id':file_id})
        return {'status':'deleted', 'file_id':file_id, 'cleanup_status':'queued'}
