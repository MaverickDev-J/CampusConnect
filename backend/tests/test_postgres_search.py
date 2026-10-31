import asyncio
import os
import sys
import unittest
from sqlalchemy import text

from database.postgres import create_session_factory, principal_session
from api.services.retrieval.postgres_search import PostgresSearch

if sys.platform == "win32":
    # Psycopg requires selector I/O; Modal's Linux event loop needs no override.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL for PostgreSQL integration")
class ScopedSearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine, self.factory = create_session_factory(os.environ["TEST_DATABASE_URL"])

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_hybrid_scope_active_revision_and_namespace(self):
        vector = [1.0] + [0.0] * 1535
        async with principal_session(self.factory, "search-owner") as session:
            try:
                await session.execute(text("INSERT INTO users VALUES ('search-owner','search@example.test','Search','hash','teacher','{}')"))
                await session.execute(text("INSERT INTO classrooms(classroom_id,name,join_code,created_by) VALUES ('search-class','Search','SRCH01','search-owner')"))
                await session.execute(text("INSERT INTO files(file_id,classroom_id,original_name,storage_path,file_type,sha256_hash,uploaded_by,status,active_revision) VALUES ('search-file','search-class','Notes','/test','pdf','hash','search-owner','ready',1)"))
                await session.execute(text("INSERT INTO file_revisions VALUES ('search-file',1,'gemini-embedding-2:1536:search-v1','test','ready')"))
                await session.execute(text("INSERT INTO chunks(chunk_id,file_id,classroom_id,revision,chunk_index,text,content_hash,embedding) VALUES ('search-chunk','search-file','search-class',1,0,'Neural networks use backpropagation','hash',CAST(:v AS vector))"), {"v": str(vector)})
                search = PostgresSearch(session)
                results = await search.search("backpropagation", vector, classroom_id="search-class")
                self.assertEqual([r.chunk_id for r in results], ["search-chunk"])
                self.assertEqual(await search.search("backpropagation", vector, classroom_id="search-class", file_id="other"), [])
                other_model = PostgresSearch(session, namespace="legacy-model")
                self.assertEqual(await other_model.search("backpropagation", vector, classroom_id="search-class"), [])
                await session.execute(text("SELECT set_config('app.user_id','outsider',true)"))
                self.assertEqual(await search.search("backpropagation", vector, classroom_id="search-class"), [])
                await session.execute(text("SELECT set_config('app.user_id','search-owner',true)"))
                await session.execute(text("UPDATE files SET status='deleted' WHERE file_id='search-file'"))
                self.assertEqual(await search.search("backpropagation", vector, classroom_id="search-class"), [])
            finally:
                # This fixture is never committed, including on assertion failures.
                await session.rollback()
