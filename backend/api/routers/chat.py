"""Chat sessions, history & SSE streaming — LangGraph v2 integration."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.agent.graph import compiled_graph
from api.agent.nodes import synthesis_node_stream
from api.dependencies import get_current_user
from database.mongo import get_db
from database.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


# ── Helpers ─────────────────────────────────────────────────────────

def _sse(event_type: str, data) -> str:
    """Format a single SSE line."""
    payload = _json.dumps({"t": event_type, "d": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


# ── Request / Response models ───────────────────────────────────────

class CreateSessionBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    file_id: Optional[str] = None
    classroom_id: Optional[str] = None


class ChatMessageBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)  # Prevent 10MB query blobs
    scope_classroom_id: Optional[str] = None


class RenameSessionBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


# ── Endpoint 1: Create Session ──────────────────────────────────────

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionBody = CreateSessionBody(),
    current_user: dict = Depends(get_current_user),
):
    """Create a new chat session."""
    db = get_db()
    user_id: str = current_user["user_id"]

    if body.file_id:
        file_doc = await db.file_metadata.find_one({"file_id": body.file_id})
        if not file_doc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"File {body.file_id} not found")
        if file_doc.get("processing", {}).get("status") != "completed":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File {body.file_id} is not yet processed")

    now = datetime.now(timezone.utc)
    session_id = f"sess_{uuid4().hex[:12]}"

    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "title": body.title or "New Chat",
        "file_id": body.file_id,
        "classroom_id": body.classroom_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.chat_sessions.insert_one(session_doc)

    return {
        "session_id": session_id,
        "title": session_doc["title"],
        "file_id": body.file_id,
        "classroom_id": body.classroom_id,
        "created_at": now.isoformat(),
    }


# ── Endpoint 2: List Sessions ───────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    classroom_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return all sessions for the authenticated user, newest first."""
    db = get_db()
    query = {"user_id": current_user["user_id"]}
    if classroom_id:
        query["classroom_id"] = classroom_id

    cursor = db.chat_sessions.find(query, {"_id": 0}).sort("updated_at", -1)
    sessions = await cursor.to_list(length=200)

    for s in sessions:
        for key in ("created_at", "updated_at"):
            if isinstance(s.get(key), datetime):
                s[key] = s[key].isoformat()

    return {"sessions": sessions, "count": len(sessions)}


# ── Endpoint 3: Load History ─────────────────────────────────────────

@router.get("/sessions/{session_id}/history")
async def load_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return all messages for a session, chronologically."""
    db = get_db()
    session = await db.chat_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")

    cursor = db.chat_history.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", 1)
    messages = await cursor.to_list(length=500)

    for m in messages:
        if isinstance(m.get("timestamp"), datetime):
            m["timestamp"] = m["timestamp"].isoformat()

    return {"messages": messages, "count": len(messages)}


# ── Endpoint 4: SSE Chat (The Main Event) ───────────────────────────

@router.post("/sessions/{session_id}/message")
async def chat_message(
    session_id: str,
    body: ChatMessageBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Send a message and stream the AI response via SSE.

    Now uses the compiled LangGraph StateGraph for all pre-synthesis steps.
    SSE event types: status | thought | token | sources | done | error
    """
    db = get_db()
    user_id: str = current_user["user_id"]

    session = await db.chat_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session["user_id"] != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")

    query = body.query

    async def event_stream():
        # ── Initial state passed to the graph ──────────────────────
        initial_state: dict = {
            "query": query,
            "session_id": session_id,
            "user_id": user_id,
            "file_id": session.get("file_id"),
            "scope_classroom_id": body.scope_classroom_id or session.get("classroom_id"),
            # These will be populated by nodes:
            "user_profile": None,
            "classroom_context": None,
            "chat_history": [],
            "router_output": None,
            "reasoning": [],
            "query_embedding": None,
            "retrieved_chunks": [],
            "used_sources": [],
            "no_chunks_found": False,
            "web_search_results": [],
            "fast_reject_response": None,
            "processing_status": "starting",
            "error": None,
        }

        # ── Redis cache check ───────────────────────────────────────
        redis_client = await get_redis()
        cache_key_data = (
            f"{initial_state['scope_classroom_id'] or 'global'}"
            f":{session.get('file_id') or 'none'}"
            f":{query.strip().lower()}"
        )
        cache_key = f"chat_cache:{hashlib.sha256(cache_key_data.encode()).hexdigest()}"

        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info("[chat_message] Cache HIT")
                data = _json.loads(cached)
                yield _sse("status", "Retrieved from cache...")
                for token in data["content"].split(" "):
                    yield _sse("token", token + " ")
                    await asyncio.sleep(0.005)
                yield _sse("sources", data.get("sources", []))
                yield _sse("done", "")
                return
        except Exception as ce:
            logger.warning("[chat_message] Cache lookup failed: %s", ce)

        try:
            # ── Run the LangGraph (entry → router → [branch] → END) ──
            yield _sse("status", "Analyzing your question...")

            final_state: dict = initial_state.copy()

            # Stream through graph nodes, emitting status events
            STATUS_MESSAGES = {
                "routing": "Understanding your question...",
                "routing_complete": "Routing...",
                "embedded": "Searching knowledge base...",
                "generating": "Preparing answer...",
                "rejected": None,  # Handled specially
            }

            async for graph_step in compiled_graph.astream(
                initial_state,
                config={"recursion_limit": 20},
            ):
                # graph_step is {node_name: state_update_dict}
                for node_name, node_output in graph_step.items():
                    final_state.update(node_output)

                    # Emit status if processing_status changed
                    new_status = node_output.get("processing_status")
                    if new_status and new_status in STATUS_MESSAGES:
                        msg = STATUS_MESSAGES[new_status]
                        if msg:
                            yield _sse("status", msg)

                    # Emit thoughts from router/retriever reasoning
                    for thought in node_output.get("reasoning", []):
                        yield _sse("thought", thought)

            # ── Check if fast_reject fired ──────────────────────────
            if final_state.get("fast_reject_response"):
                reject_msg = final_state["fast_reject_response"]
                yield _sse("status", "")
                # Stream the refusal token by token for visual consistency
                for word in reject_msg.split(" "):
                    yield _sse("token", word + " ")
                yield _sse("sources", [])
                yield _sse("done", "")

                # Save the rejection to history
                now = datetime.now(timezone.utc)
                await db.chat_history.insert_many([
                    {"session_id": session_id, "user_id": user_id, "role": "user",
                     "content": query, "timestamp": now},
                    {"session_id": session_id, "user_id": user_id, "role": "assistant",
                     "content": reject_msg, "sources": [], "intent": "OUT_OF_SCOPE", "timestamp": now},
                ])
                await db.chat_sessions.update_one(
                    {"session_id": session_id}, {"$set": {"updated_at": now}}
                )
                return

            # ── Check for error from graph ──────────────────────────
            if final_state.get("error"):
                yield _sse("error", final_state["error"])
                yield _sse("done", "")
                return

            # ── Step 2: Stream synthesis tokens ────────────────────
            yield _sse("status", "Generating answer...")

            accumulated: list[str] = []
            async for token in synthesis_node_stream(final_state):
                accumulated.append(token)
                yield _sse("token", token)

            full_response = "".join(accumulated)

            # ── Step 3: Persist to MongoDB ──────────────────────────
            now = datetime.now(timezone.utc)
            intent = final_state.get("router_output").intent if final_state.get("router_output") else "UNKNOWN"
            used_sources = final_state.get("used_sources", [])

            await db.chat_history.insert_many([
                {
                    "session_id": session_id, "user_id": user_id, "role": "user",
                    "content": query, "timestamp": now,
                },
                {
                    "session_id": session_id, "user_id": user_id, "role": "assistant",
                    "content": full_response,
                    "sources": used_sources,   # Only threshold-passing sources
                    "intent": intent,
                    "timestamp": now,
                },
            ])
            await db.chat_sessions.update_one(
                {"session_id": session_id}, {"$set": {"updated_at": now}}
            )

            # ── Step 4: Cache the response ──────────────────────────
            # Only cache RAG/CONVERSATIONAL — web search results age out quickly
            if intent in ("RAG_SEARCH", "CONVERSATIONAL"):
                try:
                    await redis_client.setex(
                        cache_key,
                        86400,  # 24h TTL
                        _json.dumps({"content": full_response, "sources": used_sources}),
                    )
                except Exception as ce:
                    logger.warning("[chat_message] Cache write failed: %s", ce)

            # ── Step 5: Emit used_sources + done ───────────────────
            yield _sse("sources", used_sources)
            yield _sse("done", "")

        except Exception as exc:
            logger.exception("[chat_message] Stream error: %s", exc)
            yield _sse("error", f"Something went wrong: {str(exc)[:200]}")
            yield _sse("done", "")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Endpoint 5: Delete Session ──────────────────────────────────────

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a chat session and all its messages."""
    db = get_db()
    session = await db.chat_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")

    await db.chat_history.delete_many({"session_id": session_id})
    await db.chat_sessions.delete_one({"session_id": session_id})
    return {"status": "deleted", "session_id": session_id}


# ── Endpoint 6: Rename Session ──────────────────────────────────────

@router.put("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    body: RenameSessionBody,
    current_user: dict = Depends(get_current_user),
):
    """Rename a chat session title."""
    db = get_db()
    session = await db.chat_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this session")

    await db.chat_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"title": body.title, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"status": "renamed", "title": body.title}
