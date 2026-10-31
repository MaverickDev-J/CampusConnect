"""Restart-safe ingestion worker with leased jobs and per-chunk checkpoints."""
import asyncio
import hashlib
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy import text
from database.postgres import principal_session
from core.gemini_budget import budget_scope, BudgetExhausted, ProviderUnavailable


def split_pages(pages, words=300, overlap=40):
    """Preserve verified page provenance; keep paragraph text in bounded windows."""
    for content, page_number in pages:
        tokens = re.findall(r"\S+", content)
        for start in range(0, len(tokens), words-overlap):
            yield " ".join(tokens[start:start+words]), page_number


async def extract_pages(path, file_type):
    if file_type == "pdf":
        def extract_pdf():
            import fitz
            with fitz.open(path) as document:
                return [(page.get_text(), number) for number, page in enumerate(document, 1)]
        pages = await asyncio.to_thread(extract_pdf)
        if pages and all(content.strip() for content, _ in pages):
            return pages, "pymupdf_text_only"
    # Existing multimodal cascade handles scans, images, and videos. Its output
    # cannot provide verified page provenance, so retain an explicit null page.
    from api.services.ingestion import _extract_text_tiered
    content, method = await _extract_text_tiered(str(path), file_type)
    return [(content, None)], method


class IngestionWorker:
    def __init__(self, factory, embeddings, storage_root, extractor=extract_pages, *, budget=None):
        self.factory, self.embeddings = factory, embeddings
        self.storage_root, self.extractor = Path(storage_root).resolve(), extractor
        self.budget = budget

    async def _lease(self, session, job):
        leased = (await session.execute(text("""SELECT file_id FROM ingestion_jobs
          WHERE file_id=:file_id AND lease_token=:lease_token AND state='working'
          AND lease_until>now() FOR UPDATE"""), job)).first()
        if not leased:
            raise RuntimeError("Ingestion lease lost")
        await session.execute(text("UPDATE ingestion_jobs SET lease_until=now()+interval '15 minutes' WHERE file_id=:file_id"), job)

    async def run_once(self):
        async with self.factory() as session, session.begin():
            job = (await session.execute(text("SELECT * FROM public.claim_ingestion_job(:token)"), {"token": uuid4().hex})).mappings().first()
        if not job:
            return False
        job = dict(job)
        actor = job["actor_id"]
        try:
            async with principal_session(self.factory, actor) as session:
                await self._lease(session, job)
                file = (await session.execute(text("SELECT * FROM files WHERE file_id=:file_id AND status<>'deleted'"), job)).mappings().one()
                allowed = (await session.execute(text("SELECT public.can_write_classroom(:id)"), {"id": file["classroom_id"]})).scalar_one()
                if not allowed:
                    raise RuntimeError("Upload permission revoked")
                await session.execute(text("UPDATE files SET status='processing',processing_error=NULL WHERE file_id=:file_id"), job)
                await session.execute(text("""INSERT INTO file_revisions(file_id,revision,embedding_namespace,chunking_version,status)
                  VALUES (:file_id,1,:namespace,'page-words300-overlap40-v1','pending') ON CONFLICT DO NOTHING"""),
                  {**job, "namespace": self.embeddings.settings.namespace})
                namespace = (await session.execute(text("SELECT embedding_namespace FROM file_revisions WHERE file_id=:file_id AND revision=1"), job)).scalar_one()
                if namespace != self.embeddings.settings.namespace:
                    raise RuntimeError("A new revision is required for this embedding model")
                saved = (await session.execute(text("SELECT count(*) FROM chunks WHERE file_id=:file_id AND revision=1"), job)).scalar_one()
            if not saved:
                path = Path(file["storage_path"]).resolve()
                if not path.is_relative_to(self.storage_root):
                    raise ValueError("Invalid storage path")
                with budget_scope(self.budget, 'extract'):
                    pages, method = await self.extractor(path, file["file_type"])
                chunks = list(split_pages(pages))
                if not chunks:
                    raise ValueError("Extraction returned no text")
                async with principal_session(self.factory, actor) as session:
                    await self._lease(session, job)
                    for index, (content, page) in enumerate(chunks):
                        await session.execute(text("""INSERT INTO chunks(chunk_id,file_id,classroom_id,revision,chunk_index,title,text,content_hash,page_number,extraction_method)
                          VALUES (:id,:file_id,:classroom,1,:index,:title,:content,:hash,:page,:method) ON CONFLICT DO NOTHING"""),
                          {**job, "id": f"{job['file_id']}:r1:c{index}", "classroom": file["classroom_id"], "index": index,
                           "title": file["original_name"], "content": content, "hash": hashlib.sha256(content.encode()).hexdigest(),
                           "page": page, "method": method})
            async with principal_session(self.factory, actor) as session:
                pending = (await session.execute(text("SELECT chunk_id,text FROM chunks WHERE file_id=:file_id AND revision=1 AND embedding IS NULL ORDER BY chunk_index"), job)).mappings().all()
            for chunk in pending:
                vector = await self.embeddings.document(chunk["text"], file["original_name"])
                async with principal_session(self.factory, actor) as session:
                    await self._lease(session, job)
                    await session.execute(text("UPDATE chunks SET embedding=CAST(:vector AS vector) WHERE chunk_id=:id"),
                                          {"id": chunk["chunk_id"], "vector": str(vector)})
            async with principal_session(self.factory, actor) as session:
                await self._lease(session, job)
                missing = (await session.execute(text("SELECT count(*) FROM chunks WHERE file_id=:file_id AND revision=1 AND embedding IS NULL"), job)).scalar_one()
                if missing:
                    raise RuntimeError("Embedding job incomplete")
                await session.execute(text("UPDATE file_revisions SET status='ready' WHERE file_id=:file_id AND revision=1"), job)
                await session.execute(text("UPDATE files SET status='ready',active_revision=1,processing_error=NULL WHERE file_id=:file_id AND status<>'deleted'"), job)
                await session.execute(text("UPDATE ingestion_jobs SET state='completed',lease_until=NULL,last_error=NULL WHERE file_id=:file_id"), job)
        except (BudgetExhausted, ProviderUnavailable) as exc:
            async with self.factory() as session, session.begin():
                if isinstance(exc, BudgetExhausted) or exc.status == 429:
                    await session.execute(text('SELECT public.defer_ingestion_job(:file_id,:lease_token,:delay)'),
                        {**job, 'delay': max(1,min(86400,exc.retry_after))})
                else:
                    await session.execute(text('SELECT public.fail_ingestion_job(:file_id,:lease_token)'), job)
        except Exception:
            # Retain successful chunks for retry. Never persist raw provider errors,
            # which may contain document content, paths, or credential details.
            async with self.factory() as session, session.begin():
                await session.execute(text("SELECT public.fail_ingestion_job(:file_id,:lease_token)"), job)
        return True
