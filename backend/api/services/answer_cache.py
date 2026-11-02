"""Exact answer reuse with fresh scope, corpus and source checks on every hit."""
import hashlib
import hmac
import json

from sqlalchemy import text
from core.config import settings
from database.postgres import principal_session

CONFIG_VERSION='embedding2-1536:hybrid-rrf60-depth12:rerank-listwise-v1:gemini-3.8-flash:synthesis-v1'


def digest(value):
    return hmac.new(settings.JWT_SECRET.encode(),json.dumps(value,sort_keys=True,default=str).encode(),hashlib.sha256).hexdigest()


class AnswerCache:
    def __init__(self,factory,*,config_version=CONFIG_VERSION):
        self.factory=factory
        self.config_version=config_version
        from api.agent.grounding import GROUNDED_SYSTEM_PROMPT,ANSWER_POLICY_VERSION
        self.prompt_hash=hashlib.sha256((ANSWER_POLICY_VERSION+GROUNDED_SYSTEM_PROMPT).encode()).hexdigest()

    async def context(self,session,state):
        row=(await session.execute(text('''SELECT c.classroom_id,v.version AS corpus_version,c.name,c.subject,c.description,
          u.name AS actor_name,u.role,m.joined_at FROM classrooms c
          JOIN classroom_corpora v ON v.classroom_id=c.classroom_id
          JOIN users u ON u.user_id=:actor LEFT JOIN classroom_members m
          ON m.classroom_id=c.classroom_id AND m.user_id=u.user_id
          WHERE c.classroom_id=:classroom AND public.can_read_classroom(c.classroom_id)'''),
          {'actor':state['user_id'],'classroom':state['scope_classroom_id']})).mappings().first()
        if not row:
            return None
        if state.get('file_id'):
            file=(await session.execute(text("SELECT file_id FROM files WHERE file_id=:file AND classroom_id=:classroom AND status='ready'"),
                {'file':state['file_id'],'classroom':state['scope_classroom_id']})).first()
            if not file:
                return None
        history=[{'role':m.role,'content':m.content} for m in state.get('chat_history',[])]
        return digest({'actor':state['user_id'],'file':state.get('file_id'),'context':dict(row),
                       'history':history,'config':self.config_version,'system_prompt':self.prompt_hash})

    async def get(self,state):
        async with principal_session(self.factory,state['user_id']) as session:
            context=await self.context(session,state)
            if not context:
                return None,None
            key=digest([context,state['query'].strip()])
            row=(await session.execute(text('SELECT answer,sources FROM answer_cache WHERE cache_key=:key AND context_key=:context AND expires_at>now()'),
                {'key':key,'context':context})).mappings().first()
            if not row or not await self.valid_sources(session,state,row['sources']):
                return context,None
            if await self.context(session,state)!=context:
                return None,None
            return context,dict(row)

    async def valid_sources(self,session,state,sources):
        ids=[s['chunk_id'] for s in sources]
        if not ids:
            return False
        rows=(await session.execute(text('''SELECT c.chunk_id FROM chunks c JOIN files f ON f.file_id=c.file_id
          JOIN file_revisions r ON r.file_id=c.file_id AND r.revision=c.revision
          WHERE c.chunk_id=ANY(CAST(:ids AS text[])) AND c.classroom_id=:classroom
          AND f.status='ready' AND f.active_revision=c.revision AND r.status='ready'
          AND r.embedding_namespace='gemini-embedding-2:1536:search-v1'
          AND (CAST(:file AS text) IS NULL OR c.file_id=:file)'''),
          {'ids':ids,'classroom':state['scope_classroom_id'],'file':state.get('file_id')})).all()
        return len(rows)==len(set(ids))

    async def put(self,state,answer):
        context=state.get('cache_context')
        intent=getattr(state.get('router_output'),'intent',None)
        if not context or not answer or len(answer)>100000 or intent not in ('RAG_SEARCH','DEEP_STUDY') or not state.get('used_sources'):
            return
        try:
            async with principal_session(self.factory,state['user_id']) as session:
                if await self.context(session,state)!=context or not await self.valid_sources(session,state,state['used_sources']):
                    return
                await session.execute(text('''INSERT INTO answer_cache(cache_key,actor_id,classroom_id,context_key,answer,sources)
                  VALUES (:key,:actor,:classroom,:context,:answer,CAST(:sources AS jsonb))
                  ON CONFLICT(cache_key) DO UPDATE SET answer=excluded.answer,sources=excluded.sources,
                    created_at=now(),expires_at=now()+interval '15 minutes' '''),
                  {'key':digest([context,state['query'].strip()]),'actor':state['user_id'],'classroom':state['scope_classroom_id'],
                   'context':context,'answer':answer,'sources':json.dumps(state['used_sources'])})
        except Exception:
            pass
