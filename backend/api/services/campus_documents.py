"""Bounded, principal-scoped document operations shared by workflows and MCP."""
from fastapi import HTTPException
from sqlalchemy import text

from database.postgres import principal_session


class CampusDocuments:
    def __init__(self, factory, rag, files):
        self.factory, self.rag, self.files = factory, rag, files

    async def list_courses(self, principal, *, offset=0, limit=50):
        async with principal_session(self.factory, principal['user_id']) as session:
            rows = (await session.execute(text('''SELECT classroom_id,name,subject,description
              FROM classrooms ORDER BY name,classroom_id LIMIT :limit OFFSET :offset'''),
              {'limit': limit, 'offset': offset})).mappings().all()
            return {'courses': [dict(row) for row in rows], 'offset': offset, 'limit': limit}

    async def search(self, principal, classroom_id, query, *, rerank=True):
        await self.files.authorize(principal, classroom_id)
        state = {'user_id': principal['user_id'], 'scope_classroom_id': classroom_id, 'query': query,
                 'skip_rerank':not rerank}
        state.update(await self.rag.embed(state))
        result = await self.rag.retrieve(state)
        ids = [source['chunk_id'] for source in result['used_sources']]
        async with principal_session(self.factory, principal['user_id']) as session:
            # Reauthorize after provider I/O and return only the current revision.
            await self.files.authorize_in_session(session, classroom_id)
            rows = (await session.execute(text('''SELECT c.chunk_id,c.file_id,c.revision,c.page_number,
              c.text,c.content_hash,f.original_name AS file_name FROM chunks c
              JOIN files f ON f.file_id=c.file_id JOIN file_revisions r ON r.file_id=c.file_id AND r.revision=c.revision
              WHERE c.chunk_id=ANY(CAST(:ids AS text[])) AND c.classroom_id=:classroom
              AND f.status='ready' AND f.active_revision=c.revision AND r.status='ready'
              AND r.embedding_namespace=:namespace'''), {'ids': ids, 'classroom': classroom_id,
              'namespace': self.rag.embeddings.settings.namespace})).mappings().all() if ids else []
        mapping = {row['chunk_id']: dict(row) for row in rows}
        return {'sources': [mapping[cid] for cid in ids if cid in mapping],
                'fallback_reason': result.get('rerank_fallback_reason')}

    async def get_document(self, principal, classroom_id, file_id, *, offset=0, limit=3):
        await self.files.authorize(principal, classroom_id)
        async with principal_session(self.factory, principal['user_id']) as session:
            file = (await session.execute(text('''SELECT file_id,original_name,status,active_revision FROM files
              WHERE file_id=:file AND classroom_id=:classroom AND status<>'deleted' '''),
              {'file': file_id, 'classroom': classroom_id})).mappings().first()
            if not file:
                raise HTTPException(404, 'Document not found')
            rows = (await session.execute(text('''SELECT chunk_id,chunk_index,page_number,text FROM chunks
              WHERE file_id=:file AND revision=:revision AND :ready
              ORDER BY chunk_index LIMIT :limit OFFSET :offset'''),
              {'file': file_id, 'revision': file['active_revision'], 'ready': file['status'] == 'ready',
               'limit': limit, 'offset': offset})).mappings().all()
            return {'file_id': file_id, 'file_name': file['original_name'], 'status': file['status'],
                    'revision': file['active_revision'], 'chunks': [dict(row) for row in rows],
                    'offset': offset, 'limit': limit}
