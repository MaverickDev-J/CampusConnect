"""Real PostgreSQL checkpoint, review, restart, and MCP transport boundaries."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import psycopg
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from sqlalchemy import text
from langgraph.types import Command

from api.agent.faculty_workflow import DraftContent, FacultyWorkflow
from database.postgres import principal_session
from mcp_server.auth import AUDIENCE, ISSUER, issue_mcp_token
from core.config import settings
from tests.test_postgres_api import PostgresApiFixture


class FacultyWorkflowTests(PostgresApiFixture):
    async def course(self):
        self.teacher, self.headers = await self.account('faculty', 'teacher')
        self.student, self.student_headers = await self.account('student')
        self.outsider, self.outsider_headers = await self.account('outsider', 'teacher')
        self.classroom = (await self.client.post('/api/classrooms', headers=self.headers, json={'name': 'ML'})).json()
        self.cid = self.classroom['classroom_id']
        await self.client.post('/api/classrooms/join', headers=self.student_headers, json={'join_code': self.classroom['join_code']})
        self.file_id, self.chunk_id = 'wf_file_' + self.tag, 'wf_chunk_' + self.tag
        vector = '[' + ','.join(['1'] + ['0'] * 1535) + ']'
        with psycopg.connect(self.owner_url) as conn:
            conn.execute('''INSERT INTO files(file_id,classroom_id,original_name,storage_path,file_type,sha256_hash,uploaded_by,status)
              VALUES (%s,%s,'ML notes.pdf','/test','pdf',%s,%s,'ready')''', (self.file_id,self.cid,self.tag,self.teacher['user_id']))
            conn.execute("INSERT INTO file_revisions VALUES (%s,1,'gemini-embedding-2:1536:search-v1','test','ready')", (self.file_id,))
            conn.execute('''INSERT INTO chunks(chunk_id,file_id,classroom_id,revision,chunk_index,text,content_hash,page_number,embedding)
              VALUES (%s,%s,%s,1,0,'Backpropagation computes gradients using the chain rule','source-hash',2,%s::vector)''',
              (self.chunk_id,self.file_id,self.cid,vector))
            conn.execute('UPDATE files SET active_revision=1 WHERE file_id=%s', (self.file_id,))
        # Real lexical retrieval, controlled generation; no external API calls.
        self.app.state.rag.embeddings.query = AsyncMock(side_effect=RuntimeError('Provider unavailable'))
        self.app.state.workflows.generator = AsyncMock(return_value=DraftContent(title='Backpropagation revision',
            announcement='Review gradients and the chain rule.', description='Discuss gradients from the course notes.'))
        self.body = {'classroom_id': self.cid, 'topic': 'backpropagation',
                     'date': (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()}

    async def draft(self):
        response = await self.client.post('/api/workflows/revision', headers=self.headers, json=self.body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def review_body(draft):
        return {key: draft[key] for key in ('version','payload_hash')}

    async def test_persistent_review_restart_and_concurrent_execution(self):
        await self.course()
        draft = await self.draft()
        path = '/api/workflows/' + draft['workflow_id']
        self.assertEqual(draft['status'], 'awaiting_approval')
        self.assertEqual(draft['sources'][0]['page_number'], 2)
        self.assertEqual((await self.client.post(path+'/execute', headers=self.headers)).status_code, 409)
        # Rebuild the service: graph state is exclusively in PostgreSQL.
        self.app.state.workflows = FacultyWorkflow(self.app.state.accounts.factory, self.app.state.workflows.documents,
                                                   self.app.state.actions, self.app.state.workflows.generator)
        approved = await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))
        self.assertEqual(approved.status_code, 200, approved.text)
        results = await asyncio.gather(*(self.client.post(path+'/execute', headers=self.headers) for _ in range(2)))
        self.assertEqual(results[0].status_code, 200, results[0].text)
        self.assertEqual(results[0].json()['result'], results[1].json()['result'])
        self.assertEqual(results[0].json()['status'], 'completed')
        self.assertEqual((await self.client.get(f'/api/announcements/{self.cid}', headers=self.headers)).json()['total'], 1)
        self.assertEqual(len((await self.client.get('/api/calendar/events', headers=self.headers)).json()['events']), 1)
        with psycopg.connect(self.owner_url) as conn:
            self.assertGreater(conn.execute('SELECT count(*) FROM checkpoints WHERE thread_id=%s', (draft['workflow_id'],)).fetchone()[0], 1)

    async def test_edits_revoke_approval_and_stale_review_is_rejected(self):
        await self.course()
        draft = await self.draft()
        path = '/api/workflows/' + draft['workflow_id']
        self.assertEqual((await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))).status_code, 200)
        edited = await self.client.patch(path, headers=self.headers, json={**self.review_body(draft),
            'payload': {**draft['payload'], 'title': 'Edited revision'}})
        self.assertEqual(edited.status_code, 200, edited.text)
        current = edited.json()
        self.assertEqual(current['version'], 2)
        self.assertEqual(current['status'], 'awaiting_approval')
        self.assertIsNone(current['approved_at'])
        self.assertEqual((await self.client.post(path+'/execute', headers=self.headers)).status_code, 409)
        self.assertEqual((await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))).status_code, 409)
        await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(current))
        self.assertEqual((await self.client.post(path+'/execute', headers=self.headers)).status_code, 200)

    async def test_failure_rolls_back_actions_and_graph_then_retry_completes(self):
        await self.course()
        draft = await self.draft()
        path = '/api/workflows/' + draft['workflow_id']
        await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))
        with patch.object(self.app.state.actions, '_calendar', side_effect=RuntimeError('Failure after announcement')):
            with self.assertRaises(RuntimeError):
                await self.client.post(path+'/execute', headers=self.headers)
        self.assertEqual((await self.client.get(path, headers=self.headers)).json()['status'], 'approved')
        self.assertEqual((await self.client.get(f'/api/announcements/{self.cid}', headers=self.headers)).json()['total'], 0)
        self.assertEqual((await self.client.post(path+'/execute', headers=self.headers)).status_code, 200)

    async def test_graph_resume_cannot_bypass_approval_or_use_deleted_evidence(self):
        from fastapi import HTTPException
        await self.course()
        draft = await self.draft()
        workflow_id = draft['workflow_id']
        with self.assertRaises(HTTPException) as denied:
            async with principal_session(self.app.state.accounts.factory, self.teacher['user_id']) as session:
                graph = await self.app.state.workflows._graph(session, self.teacher)
                await graph.ainvoke(Command(resume=True), {'configurable':{'thread_id':workflow_id}}, durability='sync')
        self.assertEqual(denied.exception.status_code, 409)
        path = '/api/workflows/'+workflow_id
        await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))
        removed = await self.client.delete('/api/files/'+self.file_id, headers=self.headers)
        self.assertEqual(removed.status_code, 202, removed.text)
        self.assertEqual((await self.client.post(path+'/execute', headers=self.headers)).status_code, 409)
        self.assertEqual((await self.client.get(f'/api/announcements/{self.cid}', headers=self.headers)).json()['total'], 0)

    async def test_expiration_source_changes_rejection_and_membership_revocation(self):
        await self.course()
        draft = await self.draft()
        path = '/api/workflows/' + draft['workflow_id']
        self.assertEqual((await self.client.get(path, headers=self.outsider_headers)).status_code, 404)
        self.assertEqual((await self.client.get(path, headers=self.student_headers)).status_code, 404)
        self.assertEqual((await self.client.post('/api/workflows/revision', headers=self.student_headers, json=self.body)).status_code, 403)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE chunks SET content_hash='changed' WHERE chunk_id=%s", (self.chunk_id,))
        self.assertEqual((await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))).status_code, 409)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE chunks SET content_hash='source-hash' WHERE chunk_id=%s", (self.chunk_id,))
            conn.execute("UPDATE faculty_workflows SET expires_at=now()-interval '1 minute' WHERE workflow_id=%s", (draft['workflow_id'],))
        self.assertEqual((await self.client.post(path+'/approve', headers=self.headers, json=self.review_body(draft))).status_code, 410)
        rejected = await self.draft()
        rpath = '/api/workflows/' + rejected['workflow_id']
        await self.client.post(rpath+'/reject', headers=self.headers, json=self.review_body(rejected))
        self.assertEqual((await self.client.post(rpath+'/execute', headers=self.headers)).status_code, 409)
        with psycopg.connect(self.owner_url) as conn:
            conn.execute("UPDATE users SET role='student' WHERE user_id=%s", (self.teacher['user_id'],))
        self.assertEqual((await self.client.get(path, headers=self.headers)).status_code, 404)

    async def test_checkpoint_rls_hides_other_owners_and_clears_pool_identity(self):
        await self.course()
        draft = await self.draft()
        factory = self.app.state.accounts.factory
        async with principal_session(factory, self.outsider['user_id']) as session:
            self.assertEqual((await session.execute(text('SELECT count(*) FROM checkpoints'))).scalar_one(), 0)
            self.assertEqual((await session.execute(text('SELECT count(*) FROM checkpoint_blobs'))).scalar_one(), 0)
        async with principal_session(factory, self.teacher['user_id']) as session:
            self.assertGreater((await session.execute(text('SELECT count(*) FROM checkpoints WHERE thread_id=:id'), {'id': draft['workflow_id']})).scalar_one(), 0)
        async with factory() as session:
            self.assertEqual((await session.execute(text('SELECT count(*) FROM checkpoints'))).scalar_one(), 0)

    def mcp_client(self, token):
        def factory(**kwargs):
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), **kwargs)
        return Client(StreamableHttpTransport('http://test/mcp/', auth=token, httpx_client_factory=factory))

    async def test_mcp_protocol_auth_scope_drafts_and_approval_boundary(self):
        await self.course()
        token_response = await self.client.post('/api/mcp/token', headers=self.headers)
        self.assertEqual(token_response.status_code, 200, token_response.text)
        token = token_response.json()['access_token']
        # The MCP credential cannot call the human approval API or mint API tokens.
        self.assertEqual((await self.client.get('/api/users/me', headers={'Authorization':'Bearer '+token})).status_code, 401)
        async with self.mcp_client(token) as client:
            names = {t.name for t in await client.list_tools()}
            self.assertEqual(len(names), 6)
            self.assertFalse(any('approve' == name or name.startswith('approve_') for name in names))
            listing = (await client.call_tool('list_courses', {})).data
            self.assertEqual(listing['courses'][0]['classroom_id'], self.cid)
            self.assertNotIn('join_code', listing['courses'][0])
            found = (await client.call_tool('search_documents', {'classroom_id':self.cid,'query':'backpropagation'})).data
            self.assertEqual(found['sources'][0]['file_id'], self.file_id)
            document = (await client.call_tool('get_document', {'classroom_id':self.cid,'file_id':self.file_id})).data
            self.assertEqual(document['chunks'][0]['page_number'], 2)
            self.assertNotIn('storage_path', document)
            draft = (await client.call_tool('prepare_revision_session', self.body)).data
            with self.assertRaises(ToolError):
                await client.call_tool('execute_approved_revision_session', {'workflow_id':draft['workflow_id']})
        await self.client.post('/api/workflows/'+draft['workflow_id']+'/approve', headers=self.headers, json=self.review_body(draft))
        # New connection simulates another stateless serving container.
        async with self.mcp_client(token) as client:
            result = (await client.call_tool('execute_approved_revision_session', {'workflow_id':draft['workflow_id']})).data
            self.assertEqual(result['status'], 'completed')
        async with self.mcp_client(issue_mcp_token(self.outsider['user_id'])) as client:
            self.assertEqual((await client.call_tool('list_courses', {})).data['courses'], [])
            with self.assertRaises(ToolError):
                await client.call_tool('get_workflow_status', {'workflow_id':draft['workflow_id']})
            with self.assertRaises(ToolError):
                await client.call_tool('get_document', {'classroom_id':self.cid,'file_id':self.file_id})

    async def test_mcp_rejects_api_expired_wrong_audience_and_revoked_credentials(self):
        await self.course()
        now = datetime.now(timezone.utc)
        claims = {'sub':self.teacher['user_id'],'iss':ISSUER,'aud':AUDIENCE,'scope':'campus:tools',
                  'iat':now,'exp':now+timedelta(minutes=10)}
        invalid = [self.headers['Authorization'].split()[1],
                   jwt.encode({**claims,'aud':'wrong'},settings.JWT_SECRET,algorithm=settings.JWT_ALGORITHM),
                   jwt.encode({**claims,'scope':['campus:tools']},settings.JWT_SECRET,algorithm=settings.JWT_ALGORITHM),
                   jwt.encode({**claims,'exp':now-timedelta(seconds=1)},settings.JWT_SECRET,algorithm=settings.JWT_ALGORITHM)]
        for token in invalid:
            response = await self.client.post('/mcp/', headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream'},
                json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
            self.assertEqual(response.status_code, 401, response.text)
        token = issue_mcp_token(self.student['user_id'])
        async with self.mcp_client(token) as client:
            self.assertEqual(len((await client.call_tool('list_courses', {})).data['courses']), 1)
            with self.assertRaises(ToolError):
                await client.call_tool('prepare_revision_session', self.body)
            with psycopg.connect(self.owner_url) as conn:
                conn.execute('DELETE FROM classroom_members WHERE classroom_id=%s AND user_id=%s', (self.cid,self.student['user_id']))
            self.assertEqual((await client.call_tool('list_courses', {})).data['courses'], [])
