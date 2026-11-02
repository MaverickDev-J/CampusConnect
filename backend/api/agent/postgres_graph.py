"""PostgreSQL LangGraph: reuse routing while replacing all retrieval I/O."""
from contextlib import aclosing
import asyncio
from langgraph.graph import END, StateGraph
from sqlalchemy import text

from api.agent.nodes import AgentState, router_node, fast_reject_node, web_search_node
from api.agent.grounding import build_grounded_prompt,GROUNDED_SYSTEM_PROMPT
from api.agent.state import UserProfile, ChatMessage, RetrievedChunk
from api.agent.state import RouterOutput
from api.services.retrieval.postgres_search import PostgresSearch
from database.postgres import principal_session
from google.genai import types
from core.gemini_budget import budget_scope
from core.telemetry import stage


class PgState(AgentState):
    skip_rerank: bool
    cache_bypass: bool
    rerank_fallback_reason: str | None
    routing_fallback_reason: str | None
    cache_context: str | None
    cached_answer: str | None
    cache_status: str
    retrieval_strategy: str


class PostgresRag:
    def __init__(self, factory, embeddings, reranker=None, *, route=router_node, budget=None, cache=None, route_timeout=5):
        if not 0 < route_timeout <= 15:
            raise ValueError('Routing timeout must be positive and at most 15 seconds')
        self.factory, self.embeddings, self.reranker = factory, embeddings, reranker
        self.cache=cache
        graph = StateGraph(PgState)
        graph.add_node("entry", self.entry)
        async def scoped_router(state):
            with budget_scope(budget, 'route'), stage('routing') as event:
                try:
                    return await asyncio.wait_for(route(state),timeout=route_timeout)
                except TimeoutError:
                    event['fallback_reason']='routing_timeout'
                    return {'router_output':RouterOutput(intent='RAG_SEARCH',
                        scope_classroom_id=state['scope_classroom_id'],confidence=0.0),
                        'routing_fallback_reason':'routing_timeout',
                        'processing_status':'routing_complete'}
        graph.add_node("router", scoped_router)
        graph.add_node('cache',self.cached)
        graph.add_node("embed", self.embed)
        graph.add_node("retriever", self.retrieve)
        graph.add_node("web", web_search_node)
        graph.add_node("reject", fast_reject_node)
        graph.set_entry_point("entry")
        graph.add_edge('entry','cache')
        graph.add_conditional_edges('cache',lambda state: END if state.get('cached_answer') else 'router')
        graph.add_conditional_edges("router", lambda state: {
            "CONVERSATIONAL": END, "OUT_OF_SCOPE": "reject", "WEB_SEARCH": "web",
        }.get(state["router_output"].intent, "embed"))
        graph.add_edge("embed", "retriever")
        for node in ("retriever", "web", "reject"):
            graph.add_edge(node, END)
        self.graph = graph.compile()

    async def cached(self,state):
        if state.get('cache_bypass'):
            return {'cache_status':'bypassed'}
        if not self.cache:
            return {'cache_status':'disabled'}
        try:
            with stage('answer_cache') as event:
                context,hit=await self.cache.get(state)
                event['hit']=bool(hit)
            if hit:
                return {'cache_context':context,'cache_status':'exact','cached_answer':hit['answer'],
                        'used_sources':hit['sources'],'retrieval_strategy':'cached'}
            return {'cache_context':context,'cache_status':'miss'}
        except Exception:
            return {'cache_status':'unavailable'}

    async def entry(self, state):
        async with principal_session(self.factory, state["user_id"]) as session:
            user = (await session.execute(text("SELECT user_id,name,role FROM users WHERE user_id=:id"), {"id": state["user_id"]})).mappings().one()
            classroom = (await session.execute(text("SELECT name,subject,description FROM classrooms WHERE classroom_id=:id"), {"id": state["scope_classroom_id"]})).mappings().one()
            history = (await session.execute(text("SELECT role,content FROM chat_messages WHERE session_id=:id ORDER BY message_id DESC LIMIT 6"), {"id": state["session_id"]})).mappings().all()
        return {"user_profile": UserProfile(**dict(user), enrolled_classroom_ids=[state["scope_classroom_id"]]),
                "classroom_context": dict(classroom), "chat_history": [ChatMessage(**dict(row)) for row in reversed(history)],
                "processing_status": "routing"}

    async def embed(self, state):
        try:
            with stage('query_embedding'):
                embedding = await self.embeddings.query(state["query"])
            return {"query_embedding": embedding, "processing_status": "embedded"}
        except Exception:
            return {"query_embedding": None, "processing_status": "embedded", "rerank_fallback_reason": "embedding_unavailable"}

    async def evidence(self, state, candidates):
        if not candidates:
            return [], []
        async with principal_session(self.factory, state["user_id"]) as session:
            rows = (await session.execute(text("""SELECT c.*,f.original_name,f.file_type
              FROM chunks c JOIN files f ON f.file_id=c.file_id
              JOIN file_revisions r ON r.file_id=c.file_id AND r.revision=c.revision
              WHERE c.chunk_id=ANY(CAST(:ids AS text[])) AND c.classroom_id=:scope
              AND f.status='ready' AND f.active_revision=c.revision AND r.status='ready'
              AND r.embedding_namespace=:namespace"""),
              {"ids": [c.chunk_id for c in candidates], "scope": state["scope_classroom_id"],
               "namespace": self.embeddings.settings.namespace})).mappings().all()
        mapping = {row["chunk_id"]: row for row in rows}
        chunks, sources = [], []
        for candidate in candidates[:6]:
            row = mapping.get(candidate.chunk_id)
            if not row:
                continue
            chunks.append(RetrievedChunk(text=row["text"], source_file=row["original_name"], file_type=row["file_type"], page_number=row["page_number"]))
            sources.append({"chunk_id": row["chunk_id"], "file_id": row["file_id"], "file_name": row["original_name"],
                            "page_number": row["page_number"], "relevance_score": None, "chunk_preview": row["text"][:300]})
        return chunks, sources

    async def retrieve(self, state):
        strategy='hybrid' if state.get('query_embedding') else 'lexical'
        with stage('retrieval',strategy=strategy) as event:
            async with principal_session(self.factory, state["user_id"]) as session:
                candidates = await PostgresSearch(session).search(state["query"], state["query_embedding"],
                    classroom_id=state["scope_classroom_id"], file_id=state.get("file_id"),
                    strategy=strategy)
            event['candidate_count']=len(candidates)
        fallback = state.get("rerank_fallback_reason")
        if self.reranker and not state.get('skip_rerank'):
            with stage('reranking') as event:
                ranking = await self.reranker.rerank(state["query"], candidates)
                event['fallback_reason']=ranking.fallback_reason
            candidates, fallback = ranking.candidates, ranking.fallback_reason or fallback
        elif self.reranker and state.get('skip_rerank'):
            with stage('reranking',skipped=True,reason='caller_disabled') as event:
                event['status']='skipped'
        chunks, sources = await self.evidence(state, candidates)
        return {"retrieved_chunks": chunks, "used_sources": sources, "no_chunks_found": not chunks,
                "processing_status": "generating", "rerank_fallback_reason": fallback,'retrieval_strategy':strategy}


class GeminiAnswer:
    def __init__(self, client):
        self.client = client

    async def __call__(self, state):
        if not self.client:
            raise RuntimeError("Generation provider unavailable")
        # One model attempt: never restart a response after emitting partial text.
        stream = await self.client.aio.models.generate_content_stream(
            model="gemini-3.8-flash", contents=build_grounded_prompt(state),
            config=types.GenerateContentConfig(system_instruction=GROUNDED_SYSTEM_PROMPT,
              temperature=0.3, max_output_tokens=4096, thinking_config=types.ThinkingConfig(thinking_level="low")))
        emitted = False
        async with aclosing(stream):
            async for item in stream:
                if item.text:
                    emitted = True
                    yield item.text
        if not emitted:
            raise RuntimeError("Generation returned no answer")
