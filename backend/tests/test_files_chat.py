import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fitz
import psycopg
from psycopg import sql
from sqlalchemy import text

from tests.test_postgres_api import PostgresApiFixture as ApiFixture
from api.agent.postgres_graph import PostgresRag
from api.agent.state import RouterOutput
from api.services.postgres_ingestion import IngestionWorker
from api.services.retrieval.embeddings import EmbeddingSettings
from database.postgres import principal_session


class FakeEmbeddings:
    settings = EmbeddingSettings()

    def __init__(self):
        self.calls = 0
        self.fail_at = None

    async def document(self, content, title):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError("Synthetic provider failure")
        return [1.0] + [0.0] * 1535

    async def query(self, content):
        return [1.0] + [0.0] * 1535


async def rag_route(state):
    return {"router_output": RouterOutput(intent="RAG_SEARCH", scope_classroom_id=state["scope_classroom_id"])}


def pdf_bytes():
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40,40), "Neural networks learn using backpropagation and gradient descent.")
        return document.tobytes()


class FilesChatTests(ApiFixture):
    async def setup_course(self):
        self.pdf = pdf_bytes()
        self.teacher, self.headers = await self.account("teacher", "teacher")
        self.classroom = (await self.client.post("/api/classrooms", headers=self.headers, json={"name": "ML"})).json()
        self.cid = self.classroom["classroom_id"]

    async def upload(self, content=None, classroom_id=None):
        return await self.client.post("/api/upload/file", headers=self.headers,
          data={"classroom_id": classroom_id or self.cid}, files={"file": ("notes.pdf", self.pdf if content is None else content, "application/pdf")})

    async def worker(self, embeddings=None, extractor=None):
        # API roles must not claim work. Grant worker capabilities explicitly only
        # when constructing this test's worker; production uses a separate login.
        with psycopg.connect(self.owner_url) as connection:
            grants = (Path(__file__).parents[1] / "migrations/worker_grants.sql").read_text()
            for statement in grants.split(';'):
                if statement.strip():
                    connection.execute(statement.replace(':"runtime_role"', sql.Identifier(self.role).as_string(connection)))
        kwargs = {"extractor": extractor} if extractor else {}
        return IngestionWorker(self.app.state.accounts.factory, embeddings or FakeEmbeddings(), self.storage, **kwargs)

    async def test_upload_ingest_retrieve_stream_and_history(self):
        await self.setup_course()
        response = await self.upload()
        self.assertEqual(response.status_code, 202, response.text)
        file_id = response.json()["file_id"]
        pending = (await self.client.get(f"/api/files/{file_id}", headers=self.headers)).json()
        self.assertEqual(pending["processing"]["status"], "pending")
        worker = await self.worker()
        self.assertTrue(await worker.run_once())
        ready = (await self.client.get(f"/api/files/{file_id}", headers=self.headers)).json()
        self.assertEqual(ready["processing"]["status"], "completed")
        self.assertEqual(ready["processing"]["chunk_count"], 1)
        duplicate = await self.upload()
        self.assertEqual(duplicate.json()["file_id"], file_id)
        self.assertFalse(await worker.run_once())
        self.app.state.rag = PostgresRag(self.app.state.accounts.factory, FakeEmbeddings(), route=rag_route)
        async def answer(state):
            self.assertIn("backpropagation", state["retrieved_chunks"][0].text)
            yield "According to notes.pdf, Page 1, networks learn through backpropagation."
        self.app.state.answer = answer
        created = await self.client.post("/api/chat/sessions", headers=self.headers, json={"classroom_id": self.cid, "file_id": file_id})
        self.assertEqual(created.status_code, 201, created.text)
        sid = created.json()["session_id"]
        response = await self.client.post(f"/api/chat/sessions/{sid}/message", headers=self.headers, json={"query": "What is backpropagation?"})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertNotIn("error", [event["t"] for event in events])
        sources = next(event["d"] for event in events if event["t"] == "sources")
        self.assertEqual(sources[0]["file_id"], file_id)
        self.assertEqual(sources[0]["page_number"], 1)
        history = (await self.client.get(f"/api/chat/sessions/{sid}/history", headers=self.headers)).json()
        self.assertEqual(history["count"], 2)
        self.assertEqual(history["messages"][1]["sources"], sources)
        self.app.state.rag.embeddings.query = AsyncMock(side_effect=RuntimeError("Embedding provider unavailable"))
        lexical = await self.client.post(f"/api/chat/sessions/{sid}/message", headers=self.headers, json={"query": "backpropagation"})
        self.assertNotIn('"t": "error"', lexical.text)
        self.assertIn(file_id, lexical.text)
        async def changed_evidence(state):
            with psycopg.connect(self.owner_url) as connection:
                connection.execute("UPDATE files SET status='deleted' WHERE file_id=%s", (file_id,))
            yield "An answer that must not be persisted after evidence deletion."
        self.app.state.answer = changed_evidence
        deleted = await self.client.post(f"/api/chat/sessions/{sid}/message", headers=self.headers, json={"query": "backpropagation"})
        self.assertIn('"t": "error"', deleted.text)
        self.assertNotIn('"t": "sources"', deleted.text)
        self.assertEqual((await self.client.get(f"/api/chat/sessions/{sid}/history", headers=self.headers)).json()["count"], 4)

    async def test_upload_scope_dedup_and_download_authorization(self):
        await self.setup_course()
        response = await self.upload()
        file_id = response.json()["file_id"]
        _, outsider = await self.account("outsider", "teacher")
        denied = await self.client.post("/api/upload/file", headers=outsider, data={"classroom_id": self.cid},
                                       files={"file": ("bad.pdf", self.pdf, "application/pdf")})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual((await self.client.get(f"/api/files/{file_id}", headers=outsider)).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/files/{file_id}/download", headers=outsider)).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/files/{file_id}/download")).status_code, 401)
        self.assertEqual((await self.client.post(f"/api/files/{file_id}/retry", headers=outsider)).status_code, 404)
        own_download = await self.client.get(f"/api/files/{file_id}/download", headers=self.headers)
        self.assertEqual(own_download.status_code, 200)
        self.assertTrue(own_download.content.startswith(b'%PDF'))
        inline = await self.client.get(f"/api/files/{file_id}/download?inline=true", headers=self.headers)
        self.assertTrue(inline.headers["content-disposition"].startswith("inline"))
        self.assertEqual(inline.headers["cache-control"], "private, no-store")
        second = (await self.client.post("/api/classrooms", headers=self.headers, json={"name": "Other"})).json()
        same_content = await self.upload(classroom_id=second["classroom_id"])
        self.assertNotEqual(same_content.json()["file_id"], file_id)
        self.assertEqual(len(list(Path(self.storage).rglob('*.pdf'))), 2)
        async with self.app.state.accounts.factory() as session:
            with self.assertRaises(Exception):
                await session.execute(text("SELECT * FROM public.claim_ingestion_job('forbidden')"))

    async def test_failed_embedding_resumes_without_repeating_successful_chunks(self):
        await self.setup_course()
        file_id = (await self.upload()).json()["file_id"]
        async def pages(*args):
            return [(" ".join(['backpropagation']*600), 1)], "test"
        embeddings = FakeEmbeddings()
        embeddings.fail_at = 2
        worker = await self.worker(embeddings, pages)
        await worker.run_once()
        metadata = (await self.client.get(f"/api/files/{file_id}", headers=self.headers)).json()
        self.assertEqual(metadata["processing"]["status"], "pending")
        with psycopg.connect(self.owner_url) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM chunks WHERE file_id=%s AND embedding IS NOT NULL", (file_id,)).fetchone()[0], 1)
            connection.execute("UPDATE ingestion_jobs SET available_at=now() WHERE file_id=%s", (file_id,))
        await worker.run_once()
        self.assertEqual(embeddings.calls, 4)  # 1 saved + 1 failure + 2 remaining chunks.
        self.assertEqual((await self.client.get(f"/api/files/{file_id}", headers=self.headers)).json()["processing"]["status"], "completed")

    async def test_chat_session_owner_scope_and_failed_turn_cleanup(self):
        await self.setup_course()
        _, other = await self.account("student")
        sid = (await self.client.post("/api/chat/sessions", headers=self.headers, json={"classroom_id": self.cid})).json()["session_id"]
        self.assertEqual((await self.client.get(f"/api/chat/sessions/{sid}/history", headers=other)).status_code, 404)
        saved = await self.app.state.chat.acquire(self.teacher, sid, self.cid)
        busy = await self.client.post(f"/api/chat/sessions/{sid}/message", headers=self.headers, json={"query": "test"})
        self.assertEqual(busy.status_code, 409)
        await self.app.state.chat.release(self.teacher, saved)
        self.app.state.rag = SimpleNamespace(graph=SimpleNamespace(astream=self.broken_graph))
        response = await self.client.post(f"/api/chat/sessions/{sid}/message", headers=self.headers, json={"query": "test"})
        self.assertIn('"t": "error"', response.text)
        self.assertEqual((await self.client.get(f"/api/chat/sessions/{sid}/history", headers=self.headers)).json()["count"], 0)
        saved = await self.app.state.chat.acquire(self.teacher, sid, self.cid)
        await self.app.state.chat.release(self.teacher, saved)

    async def broken_graph(self, state):
        raise RuntimeError("Synthetic outage")
        yield {}

    async def test_expired_job_is_reclaimed_and_old_worker_cannot_fail_it(self):
        await self.setup_course()
        file_id = (await self.upload()).json()["file_id"]
        worker = await self.worker()
        async with worker.factory() as session, session.begin():
            (await session.execute(text("SELECT * FROM public.claim_ingestion_job('old-worker')"))).mappings().one()
        with psycopg.connect(self.owner_url) as connection:
            connection.execute("UPDATE ingestion_jobs SET lease_until=now()-interval '1 second' WHERE file_id=%s", (file_id,))
        await worker.run_once()
        async with worker.factory() as session, session.begin():
            await session.execute(text("SELECT public.fail_ingestion_job(:id,'old-worker')"), {"id": file_id})
        self.assertEqual((await self.client.get(f"/api/files/{file_id}", headers=self.headers)).json()["processing"]["status"], "completed")

    async def test_concurrent_workers_process_one_job_once(self):
        await self.setup_course()
        await self.upload()
        embeddings = FakeEmbeddings()
        worker = await self.worker(embeddings)
        results = await asyncio.gather(worker.run_once(), worker.run_once())
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(embeddings.calls, 1)
