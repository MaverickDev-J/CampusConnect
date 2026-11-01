"""Chat HTTP contracts and SSE backed entirely by the PostgreSQL graph."""
import asyncio
import json
import logging
from contextlib import aclosing
from pathlib import PurePath
import re
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from api.dependencies import get_current_user
from api.routers.chat import CreateSessionBody, ChatMessageBody, RenameSessionBody
from database.postgres import principal_session
from sqlalchemy import text
from core.gemini_budget import BudgetExhausted,ProviderUnavailable
from core.telemetry import RunTrace,current_trace,stage,save_trace

router = APIRouter(prefix="/api/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


def public_session(row):
    return {key: row[key] for key in ("session_id", "title", "file_id", "classroom_id", "created_at", "updated_at")}


def sse(kind, data):
    return "data: " + json.dumps({"t": kind, "d": data}, ensure_ascii=False) + "\n\n"


@router.get("/quick-prompts")
async def quick_prompts(request: Request, classroom_id: str, principal=Depends(get_current_user)):
    await request.app.state.files.authorize(principal, classroom_id)
    # Recommendations must remain available during provider outages and must
    # never spend the answer budget just because a student opens this screen.
    async with principal_session(request.app.state.chat.factory, principal['user_id']) as session:
        rows = (await session.execute(text('''SELECT f.file_id,f.original_name FROM files f
          JOIN file_revisions r ON r.file_id=f.file_id AND r.revision=f.active_revision
          WHERE f.classroom_id=:classroom AND f.status='ready' AND r.status='ready'
          AND r.embedding_namespace=:namespace
          AND EXISTS (SELECT 1 FROM chunks c WHERE c.file_id=f.file_id
            AND c.revision=f.active_revision AND c.embedding IS NOT NULL)
          ORDER BY f.uploaded_at DESC,f.file_id LIMIT 4'''),
          {'classroom':classroom_id,'namespace':request.app.state.rag.embeddings.settings.namespace})).mappings().all()
    if not rows:
        return {'prompts':[]}
    templates = [
        ('book','Summarize', 'Summarize the main concepts in {name} using the uploaded material.'),
        ('bulb','Explain', 'Explain the key terms in {name} with simple examples from the material.'),
        ('quiz','Practice', 'Create five practice questions based on {name}, with answers grounded in the material.'),
        ('review','Revise', 'Help me revise {name}: list the important concepts and explain how they relate.'),
    ]
    prompts=[]
    for index,(icon,label,template) in enumerate(templates):
        document=rows[index % len(rows)]
        name=re.sub(r'\s+',' ',PurePath(document['original_name']).stem).strip()[:90] or 'course notes'
        prompts.append({'icon':{'book':'\U0001f4d6','bulb':'\U0001f4a1','quiz':'\U0001f9e0','review':'\U0001f4dd'}[icon],
            'text':f'{label}: {name}', 'prompt':template.format(name=json.dumps(document['original_name'][:180])),
            'file_id':document['file_id']})
    return {'prompts':prompts}


@router.post("/sessions", status_code=201)
async def create(request: Request, body: CreateSessionBody = CreateSessionBody(), principal=Depends(get_current_user)):
    return public_session(await request.app.state.chat.create(principal, body))


@router.get("/sessions")
async def sessions(request: Request, classroom_id: str | None = None, principal=Depends(get_current_user)):
    rows = await request.app.state.chat.list(principal, classroom_id)
    return {"sessions": [public_session(row) for row in rows], "count": len(rows)}


@router.get("/sessions/{session_id}/history")
async def history(session_id: str, request: Request, principal=Depends(get_current_user)):
    rows = await request.app.state.chat.history(principal, session_id)
    return {"messages": rows, "count": len(rows)}


@router.put("/sessions/{session_id}")
async def rename(session_id: str, request: Request, body: RenameSessionBody, principal=Depends(get_current_user)):
    await request.app.state.chat.modify(principal, session_id, body.title)
    return {"status": "renamed", "title": body.title}


@router.delete("/sessions/{session_id}")
async def delete(session_id: str, request: Request, principal=Depends(get_current_user)):
    await request.app.state.chat.modify(principal, session_id)
    return {"status": "deleted", "session_id": session_id}


@router.post("/sessions/{session_id}/message")
async def message(session_id: str, request: Request, body: ChatMessageBody, principal=Depends(get_current_user)):
    store = request.app.state.chat
    if body.origin!='live' or body.bypass_cache:
        if principal.get('role') not in ('teacher','superadmin'):
            raise HTTPException(403,'Faculty access required for evaluation controls')
    saved = await store.acquire(principal, session_id, body.scope_classroom_id)

    async def events():
        trace=RunTrace(resource_type='chat_session',resource_id=session_id)
        trace_token=current_trace.set(trace)
        outcome='error'
        state = {"query": body.query, "session_id": session_id, "user_id": principal["user_id"],
                 "scope_classroom_id": saved["classroom_id"], "file_id": saved["file_id"], "reasoning": [],
                 "used_sources": [], "retrieved_chunks": [], "no_chunks_found": False,
                 "cache_bypass":body.bypass_cache or body.origin!='live'}
        try:
            async with asyncio.timeout(120):
                yield sse("status", "Searching course materials...")
                async for updates in request.app.state.rag.graph.astream(state):
                    for update in updates.values():
                        state.update(update)
                await request.app.state.files.authorize(principal, saved["classroom_id"])
                answer = []
                if state.get('cached_answer') or state.get("fast_reject_response"):
                    answer = [state.get('cached_answer') or state['fast_reject_response']]
                    trace.first_token()
                    yield sse("token", answer[0])
                else:
                    yield sse("status", "Generating answer...")
                    with stage('generation'):
                        async with aclosing(request.app.state.answer(state)) as tokens:
                            async for token in tokens:
                                trace.first_token()
                                answer.append(token)
                                yield sse("token", token)
                # Permission, revision, and deletion checks run again before storing
                # references or emitting source metadata to the client.
                await request.app.state.files.authorize(principal, saved["classroom_id"])
                sources = state.get("used_sources", [])
                if sources:
                    async with principal_session(store.factory, principal["user_id"]) as session:
                        active = (await session.execute(text("""SELECT count(*) FROM chunks c JOIN files f ON f.file_id=c.file_id
                          WHERE c.chunk_id=ANY(CAST(:ids AS text[])) AND f.status='ready' AND f.active_revision=c.revision"""),
                          {"ids": [source["chunk_id"] for source in sources]})).scalar_one()
                        if active != len(sources):
                            raise RuntimeError("Evidence changed during generation")
                await store.finish(principal, saved, body.query, ''.join(answer), state.get("used_sources", []))
                if not state.get('cache_bypass') and not state.get('cached_answer') and getattr(request.app.state,'answer_cache',None):
                    await request.app.state.answer_cache.put(state,''.join(answer))
                yield sse("sources", state.get("used_sources", []))
                if state.get("rerank_fallback_reason"):
                    yield sse("status", "Answer prepared from available course evidence")
                outcome='success'
                yield sse("done", "")
        except (asyncio.CancelledError,GeneratorExit):
            outcome='cancelled'
            raise
        except BudgetExhausted:
            yield sse('error', 'AI capacity is temporarily unavailable. Please try again later.')
            yield sse('done', '')
        except ProviderUnavailable:
            yield sse('error', 'The AI service is temporarily unavailable. Your course materials are saved; please try again shortly.')
            yield sse('done', '')
        except Exception:
            logger.warning("PostgreSQL chat turn failed; session=%s", session_id)
            yield sse("error", "Unable to complete this response. Please try again.")
            yield sse("done", "")
        finally:
            try:
                current_trace.reset(trace_token)
            except ValueError:
                pass
            await save_trace(store.factory,principal,saved['classroom_id'],trace,state,outcome,origin=body.origin)
            try:
                await store.release(principal, saved)
            except Exception:
                logger.warning("Could not release chat lease; it will expire")

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
