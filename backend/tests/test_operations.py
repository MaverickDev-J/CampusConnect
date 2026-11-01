"""Trace correlation and retention using real scoped PostgreSQL roles."""
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from api.services.campus_outbox import CampusOutbox
from api.services.storage_cleanup import StorageCleanup
from core.maintenance import prune_history
from database.postgres import principal_session
from tests.test_postgres_api import PostgresApiFixture
from tests import test_faculty_workflow as workflow_helpers
from tests import test_files_chat as file_helpers


class OperationsTests(PostgresApiFixture):
    course=workflow_helpers.FacultyWorkflowTests.course
    draft=workflow_helpers.FacultyWorkflowTests.draft
    review_body=staticmethod(workflow_helpers.FacultyWorkflowTests.review_body)
    setup_course=file_helpers.FilesChatTests.setup_course
    upload=file_helpers.FilesChatTests.upload
    worker=file_helpers.FilesChatTests.worker

    def grant_worker(self):
        with psycopg.connect(self.owner_url) as conn:
            statements=(Path(__file__).parents[1]/'migrations/worker_grants.sql').read_text()
            for statement in statements.split(';'):
                if statement.strip():conn.execute(statement.replace(':"runtime_role"',sql.Identifier(self.role).as_string(conn)))

    async def test_workflow_mcp_review_and_delivery_share_trace_with_scope_checks(self):
        await self.course()
        draft=await self.draft()
        trace_id=draft['trace_id'];path='/api/workflows/'+draft['workflow_id']
        await self.client.post(path+'/approve',headers=self.headers,json=self.review_body(draft))
        executed=await self.client.post(path+'/execute',headers=self.headers)
        self.assertEqual(executed.status_code,200,executed.text)
        self.grant_worker()
        dispatcher=CampusOutbox(self.app.state.accounts.factory,AsyncMock())
        for _ in range(3):
            if not await dispatcher.run_once():break
        response=await self.client.get('/api/quality/traces/'+trace_id,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        runs=response.json()['runs']
        self.assertTrue({'workflow','delivery'}<={row['kind'] for row in runs})
        stages=[event['stage'] for row in runs for event in row['events']]
        self.assertIn('mcp.client.search_documents',stages)
        self.assertIn('mcp.server.search',stages)
        self.assertIn('workflow.approve',stages)
        self.assertIn('workflow.execute',stages)
        workflow_runs=[row for row in runs if row['kind']=='workflow']
        self.assertTrue(all(row['resource_id']==draft['workflow_id'] for row in workflow_runs))
        self.assertTrue(all(row['parent_run_id'] for row in runs if row['kind']=='delivery'))
        self.assertNotIn('Backpropagation computes gradients',json.dumps(runs))
        for headers in (self.student_headers,self.outsider_headers):
            self.assertEqual((await self.client.get('/api/quality/traces/'+trace_id,headers=headers)).status_code,404)

    async def test_upload_worker_and_cleanup_trace_links_survive_queue_handoffs(self):
        await self.setup_course()
        file_id=(await self.upload()).json()['file_id']
        with psycopg.connect(self.owner_url) as conn:
            trace,parent=conn.execute('SELECT trace_id,parent_run_id FROM ingestion_jobs WHERE file_id=%s',(file_id,)).fetchone()
        self.assertTrue(trace and parent)
        await (await self.worker()).run_once()
        runs=(await self.client.get('/api/quality/traces/'+trace,headers=self.headers)).json()['runs']
        self.assertEqual(len(runs),2)
        self.assertTrue(any(row['parent_run_id']==parent for row in runs))
        self.assertTrue(all(row['resource_id']==file_id for row in runs))
        await self.client.delete('/api/files/'+file_id,headers=self.headers)
        with psycopg.connect(self.owner_url) as conn:
            cleanup_trace=conn.execute('SELECT trace_id FROM storage_cleanup WHERE file_id=%s',(file_id,)).fetchone()[0]
        self.assertTrue(cleanup_trace)
        await StorageCleanup(self.app.state.accounts.factory,self.storage).run_once()
        result=(await self.client.get('/api/quality/traces/'+cleanup_trace,headers=self.headers)).json()
        self.assertEqual(len(result['runs']),2)

    async def test_retention_is_worker_only_bounded_and_preserves_domain_records(self):
        await self.course()
        draft=await self.draft()
        async with self.app.state.accounts.factory() as session:
            with self.assertRaises(ProgrammingError):
                await session.execute(text('SELECT public.prune_ai_history(500)'))
        old='old_'+self.tag;recent='recent_'+self.tag;budget_id=uuid4()
        with psycopg.connect(self.owner_url) as conn:
            for run_id,age in ((old,20),(recent,1)):
                conn.execute("""INSERT INTO ai_runs(run_id,actor_id,classroom_id,kind,origin,status,duration_ms,created_at)
                  VALUES (%s,%s,%s,'chat','synthetic','success',1,now()-(%s*interval '1 day'))""",(run_id,self.teacher['user_id'],self.cid,age))
            conn.execute("""INSERT INTO ai_budget_calls(call_id,project_key,model,workload,reserved_input,reserved_output,created_at,
              quota_day,lease_until,finished_at,outcome) VALUES(%s,'campusconnect-default','gemini-embedding-2','embed_query',1,0,
              now()-interval '31 days',current_date-31,now()-interval '31 days',now()-interval '31 days','error')""",(budget_id,))
        self.grant_worker()
        counts=await prune_history(self.app.state.accounts.factory,batch_size=1,max_batches=1)
        self.assertEqual(counts['traces'],1)
        self.assertEqual(counts['budget_calls'],1)
        with psycopg.connect(self.owner_url) as conn:
            self.assertFalse(conn.execute('SELECT 1 FROM ai_runs WHERE run_id=%s',(old,)).fetchone())
            self.assertTrue(conn.execute('SELECT 1 FROM ai_runs WHERE run_id=%s',(recent,)).fetchone())
            self.assertTrue(conn.execute('SELECT 1 FROM faculty_workflows WHERE workflow_id=%s',(draft['workflow_id'],)).fetchone())
            self.assertTrue(conn.execute('SELECT last_cleanup_at FROM operational_settings').fetchone()[0])
        async with self.app.state.accounts.factory() as session:
            with self.assertRaises(Exception):await session.execute(text('SELECT public.prune_ai_history(0)'))
        async with self.app.state.accounts.factory() as session:
            with self.assertRaises(Exception):await session.execute(text('SELECT public.prune_ai_history(NULL)'))
