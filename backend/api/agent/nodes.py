"""
nodes.py — CampusMind LangGraph Node Definitions (Production v2)
================================================================
6 nodes. Proper separation of concerns. No wasted API calls.

NODE 1 : entry_node          — MongoDB profile + history. NO embedding.
NODE 2 : router_node         — Gemini Flash JSON mode. Classifies intent.
NODE 3 : embed_node          — Gemini Embedding. Runs ONLY on RAG/WEB path.
NODE 4A: retriever_node      — ChromaDB semantic search. Emits used_sources.
NODE 4B: web_search_node     — DuckDuckGo real-time search.
NODE 4C: fast_reject_node    — Hardcoded refusal. Zero LLM cost.
NODE 5 : synthesis_node_stream — Gemini Flash streaming (async generator,
                                  driven from SSE layer, not in the graph).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

from database.chroma import get_chroma_collection
from database.mongo import get_db
from core.llm_router import (
    call_gemini_with_fallback,
    router_key_manager,
    chat_key_manager,
    ROUTER_MODEL_CHAIN,
    CHAT_MODEL_CHAIN,
)

from .state import (
    ChatMessage,
    RetrievedChunk,
    RouterOutput,
    UserProfile,
)

# ── Typed State for LangGraph ──────────────────────────────────────────

class AgentState(TypedDict):
    """
    Structured State for the CampusMind Agent.
    In LangGraph 0.2+, using a TypedDict ensures nodes return UPDATES 
    rather than replacing the entire state.
    """
    # ── Input / Context ──
    query: str
    session_id: str
    user_id: str
    file_id: Optional[str]
    scope_classroom_id: Optional[str]
    
    # ── Enrichment (Populated by entry_node) ──
    user_profile: Optional[Any]
    classroom_context: Optional[Dict]
    chat_history: List[Any]
    
    # ── Inference (Populated by router_node) ──
    router_output: Optional[Any]
    reasoning: List[str]
    
    # ── Retrieval (Populated by embed/retriever/web) ──
    query_embedding: Optional[List[float]]
    retrieved_chunks: List[Any]
    used_sources: List[Any]
    web_search_results: List[Any]
    recent_files_context: List[Dict]  # List of most recent files in classroom
    no_chunks_found: bool
    
    # ── Flow Control ──
    processing_status: str
    fast_reject_response: Optional[str]
    error: Optional[str]


# ── Configuration ────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

EMBED_MODEL = "models/gemini-embedding-001"
# RELEVANCE_THRESHOLD: minimum cosine similarity to treat a chunk as relevant.
# Chunks below this score are silently dropped and never shown to the user.
RELEVANCE_THRESHOLD = 0.35


def _get_embed_client() -> genai.Client:
    """Get a healthy client from the CHAT pool for embeddings."""
    client, _ = chat_key_manager.get_client()
    return client


# ══════════════════════════════════════════════════════════════════════
# NODE 1: entry_node
# Loads user profile, enrolled classrooms, chat history, classroom ctx.
# Does NOT embed — embedding is deferred to embed_node on the RAG path.
# ══════════════════════════════════════════════════════════════════════

async def entry_node(state: AgentState) -> dict:
    """Enrich state with user profile, history, and classroom context."""
    logger.info("[entry_node] user=%s session=%s", state["user_id"], state["session_id"])

    db = get_db()

    # 1. User profile + enrolled classrooms
    user_doc = await db.users.find_one({"user_id": state["user_id"]})
    if not user_doc:
        logger.error("[entry_node] User %s not found", state["user_id"])
        return {"error": f"User {state['user_id']} not found"}

    classrooms_cursor = db.classrooms.find({
        "$or": [
            {"created_by": state["user_id"]},
            {"members.user_id": state["user_id"]},
        ]
    })
    classrooms = await classrooms_cursor.to_list(length=100)
    enrolled_ids = [c["classroom_id"] for c in classrooms]

    profile = UserProfile(
        user_id=user_doc["user_id"],
        name=user_doc["name"],
        role=user_doc["role"],
        enrolled_classroom_ids=enrolled_ids,
    )

    # 2. Last 6 messages (3 turns) for conversational context
    cursor = (
        db.chat_history.find({"session_id": state["session_id"]})
        .sort("timestamp", -1)
        .limit(6)
    )
    raw = await cursor.to_list(length=6)
    raw.reverse()
    chat_history = [ChatMessage(role=m["role"], content=m["content"]) for m in raw]

    # 3. Classroom context (subject, name, description for router grounding)
    classroom_context = None
    if state.get("scope_classroom_id"):
        cls_doc = await db.classrooms.find_one({"classroom_id": state["scope_classroom_id"]})
        if cls_doc:
            classroom_context = {
                "name": cls_doc.get("name"),
                "subject": cls_doc.get("subject"),
                "description": cls_doc.get("description"),
            }
            logger.info("[entry_node] Classroom context: %s (%s)", classroom_context["name"], classroom_context["subject"])

    logger.info("[entry_node] profile=%s enrolled=%d history=%d msgs",
                profile.role, len(enrolled_ids), len(chat_history))

    return {
        "user_profile": profile,
        "classroom_context": classroom_context,
        "chat_history": chat_history,
        "processing_status": "routing",
    }


# ══════════════════════════════════════════════════════════════════════
# NODE 2: router_node
# Classifies the query intent using Gemini JSON mode.
# Strict classroom-scope awareness baked into the prompt.
# ══════════════════════════════════════════════════════════════════════

ROUTER_SYSTEM_PROMPT = r"""\
You are a strict query gate for CampusAI, an AI tutor built exclusively for enrolled college students.

## YOUR ONLY JOB
Classify the user's query into ONE of 5 intents and output STRICT JSON.
Your classification determines whether an expensive LLM call is made, so be accurate.

## INTENT DEFINITIONS

### 1. CONVERSATIONAL
Pure social interaction with zero academic content.
Examples: "Hi", "Hello", "Thanks", "Goodbye", "You're great"
NOT this: "Can you help me?" (→ RAG_SEARCH), "What should I study?" (→ RAG_SEARCH)

### 2. RAG_SEARCH  [DEFAULT for academic queries]
Any question about academic concepts, course materials, subject topics, or study help.
Examples:
- "What is backpropagation?"
- "Explain page replacement algorithms"
- "What does my notes say about TCP?"
- "Summarize the recently added files"
- "Quiz me on data structures"

### 3. WEB_SEARCH
Queries about CURRENT/RECENT real-world events, news, or rapidly-changing technical developments.
The key signal: "latest", "recent", "this week", "2025", "news about", "newest version of".
Examples: "Latest LLM benchmarks", "Recent AI breakthroughs", "What's new in React 19"

### 4. OUT_OF_SCOPE  ← USE THIS AGGRESSIVELY
ANY query that is NOT directly related to academics OR the subject of the CURRENT CLASSROOM.
This includes:
- Topics completely unrelated to the classroom subject (e.g., history/war in a CS class)
- Medical advice, legal advice, personal advice
- Entertainment, sports, politics, celebrity news
- Academic cheating: "Write my assignment", "Solve this exam for me"

## CRITICAL CLASSROOM SUBJECT RULE
The user is inside a specific classroom with a defined subject.
If the query topic is NOT related to that subject, classify as OUT_OF_SCOPE.
Example: User is in "Software Engineering 2026" → asking about "Iran-Iraq War" → OUT_OF_SCOPE
Example: User is in "Machine Learning" → asking about "neural networks" → RAG_SEARCH
Example: User is in "Data Structures" → asking about "backpropagation" → RAG_SEARCH (still academic, cross-topic is ok)

### 5. DEEP_STUDY  [Rare]
User explicitly references a specific file by name or ID they want to study.
Examples: "Summarize this PDF: lecture_3.pdf", "Quiz me on unit4_notes.pdf"

## OUTPUT FORMAT (strict JSON, no markdown fences)
{
  "intent": "RAG_SEARCH" | "WEB_SEARCH" | "DEEP_STUDY" | "CONVERSATIONAL" | "OUT_OF_SCOPE",
  "scope_classroom_id": "<classroom_id or null>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence explaining your classification>"
}

SCOPE RULE: If intent needs classroom context, use the CURRENT CLASSROOM ID from context. Null if uncertain.
"""


async def router_node(state: AgentState) -> dict:
    """Classify query intent. Strict scope-awareness baked into prompt."""
    logger.info("[router_node] query=%s", state["query"][:80])

    profile: UserProfile = state["user_profile"]
    ctx = state.get("classroom_context") or {}

    # Build rich context for the router
    classroom_line = ""
    if ctx:
        classroom_line = (
            f"CURRENT CLASSROOM: {ctx.get('name')} | Subject: {ctx.get('subject')}\n"
            f"CLASSROOM DESCRIPTION: {ctx.get('description', 'N/A')}\n"
        )

    history_snippet = ""
    if state.get("chat_history"):
        recent = state["chat_history"][-2:]
        history_snippet = "\nRECENT CONVERSATION:\n" + "\n".join(
            f"{m.role.upper()}: {m.content[:150]}" for m in recent
        )

    # Deduplicate full_prompt assignment (was a copy-paste bug in v1)
    full_prompt = (
        f"{classroom_line}"
        f"USER ROLE: {profile.role}\n"
        f"{history_snippet}\n\n"
        f"QUERY TO CLASSIFY: {state['query']}"
    )

    try:
        response = await call_gemini_with_fallback(
            model_chain=ROUTER_MODEL_CHAIN,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=ROUTER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=150,
            ),
            key_pool=router_key_manager,  # Use the cheap isolated ROUTER pool
        )
    except Exception as e:
        logger.warning("[router_node] All models failed: %s — fallback RAG_SEARCH", e)
        response = None

    if response and getattr(response, "text", None):
        try:
            parsed = json.loads(response.text.strip())
            intent = parsed.get("intent", "RAG_SEARCH")

            # Safety: if intent is not a known value, default to OUT_OF_SCOPE
            valid = {"RAG_SEARCH", "WEB_SEARCH", "DEEP_STUDY", "CONVERSATIONAL", "OUT_OF_SCOPE"}
            if intent not in valid:
                intent = "OUT_OF_SCOPE"

            router_output = RouterOutput(
                intent=intent,
                scope_classroom_id=parsed.get("scope_classroom_id") or state.get("scope_classroom_id"),
                confidence=parsed.get("confidence", 0.9),
                reasoning=[parsed.get("reasoning", f"Classified as {intent}")],
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("[router_node] JSON parse error: %s — fallback RAG_SEARCH", e)
            router_output = RouterOutput(intent="RAG_SEARCH", confidence=0.0)
    else:
        logger.warning("[router_node] No response — fallback RAG_SEARCH")
        router_output = RouterOutput(intent="RAG_SEARCH", confidence=0.0)

    logger.info("[router_node] intent=%s conf=%.2f reason=%s",
                router_output.intent, router_output.confidence or 0,
                router_output.reasoning[0][:80] if router_output.reasoning else "")

    return {
        "router_output": router_output,
        "reasoning": router_output.reasoning,
        "processing_status": "routing_complete",
    }


# ══════════════════════════════════════════════════════════════════════
# NODE 3: fast_reject_node
# Zero-cost hardcoded refusal. No Gemini call. No embedding.
# Used for OUT_OF_SCOPE intent.
# ══════════════════════════════════════════════════════════════════════

async def fast_reject_node(state: dict) -> dict:
    """Return a hardcoded refusal. No LLM, no cost, no latency."""
    ctx = state.get("classroom_context") or {}
    subject = ctx.get("subject", "your enrolled courses")
    classroom_name = ctx.get("name", "this classroom")

    message = (
        f"I'm CampusAI, designed specifically to help you study **{subject}** in **{classroom_name}**. "
        f"That question falls outside what I can assist with here.\n\n"
        f"Feel free to ask me anything about your course materials — concepts, summaries, quizzes, or explanations! 📚"
    )

    logger.info("[fast_reject_node] Rejecting out-of-scope query")
    return {
        "fast_reject_response": message,
        "processing_status": "rejected",
    }


# ══════════════════════════════════════════════════════════════════════
# NODE 4: embed_node
# Generates a query embedding ONLY when retrieval is needed.
# Skipped entirely for CONVERSATIONAL and OUT_OF_SCOPE.
# ══════════════════════════════════════════════════════════════════════

async def embed_node(state: dict) -> dict:
    """Generate query embedding for RAG and WEB_SEARCH paths."""
    logger.info("[embed_node] Embedding query...")
    client = _get_embed_client()

    try:
        embed_result = await client.aio.models.embed_content(
            model=EMBED_MODEL,
            contents=state["query"],
            config={"task_type": "RETRIEVAL_QUERY"},
        )
        query_embedding = list(embed_result.embeddings[0].values)
        logger.info("[embed_node] %d-dim embedding generated", len(query_embedding))
        return {
            "query_embedding": query_embedding,
            "processing_status": "embedded",
        }
    except Exception as e:
        logger.error("[embed_node] Embedding failed: %s", e)
        return {
            "query_embedding": [],
            "error": f"Embedding failed: {e}",
        }


async def _fetch_recent_files_metadata(classroom_id: str, limit: int = 5) -> List[Dict]:
    """Fetch metadata for the most recently uploaded files in a classroom."""
    db = get_db()
    cursor = (
        db.file_metadata.find(
            {"classroom_id": classroom_id, "processing.status": "completed"},
            {"file_id": 1, "original_name": 1, "uploaded_at": 1, "file_type": 1, "_id": 0}
        )
        .sort("uploaded_at", -1)
        .limit(limit)
    )
    files = await cursor.to_list(length=limit)
    for f in files:
        if isinstance(f.get("uploaded_at"), datetime):
            f["uploaded_at"] = f["uploaded_at"].strftime("%Y-%m-%d %H:%M")
    return files


# ══════════════════════════════════════════════════════════════════════
# NODE 5A: retriever_vector_node
# Semantic search in ChromaDB. Applies relevance threshold.
# Also fetches recent metadata for temporal queries.
# ══════════════════════════════════════════════════════════════════════

async def retriever_vector_node(state: dict) -> dict:
    """
    Query ChromaDB for top 8 chunks. Filter by RELEVANCE_THRESHOLD.
    Only emits chunks that actually passed into used_sources.
    """
    logger.info("[retriever_node] Starting ChromaDB retrieval")

    scope: RouterOutput = state["router_output"]
    profile: UserProfile = state["user_profile"]
    query_text = state["query"].lower()
    collection = get_chroma_collection()
    reasoning_msg = "Searching course materials..."
    recent_files = []

    # ── Check if user is asking for recent materials ──────────────────
    temporal_keywords = ["recent", "new", "latest", "upload", "added", "update", "list files"]
    is_temporal = any(k in query_text for k in temporal_keywords)
    
    target_cls = scope.scope_classroom_id or state.get("scope_classroom_id")
    if is_temporal and target_cls:
        logger.info("[retriever_node] Temporal query detected — fetching metadata")
        recent_files = await _fetch_recent_files_metadata(target_cls)

    if not state.get("query_embedding"):
        logger.error("[retriever_node] No query_embedding in state — embed_node must have failed")
        return {
            "retrieved_chunks": [], "used_sources": [], "no_chunks_found": True,
            "processing_status": "generating",
        }

    # ── Build where filter ────────────────────────────────────────
    file_id = state.get("file_id")
    if file_id:
        where_filter = {"file_id": {"$eq": file_id}}
        reasoning_msg = "Searching within specific file..."
    else:
        # Priority: router scope → session scope → all enrolled
        target_cls = scope.scope_classroom_id or state.get("scope_classroom_id")

        if target_cls and target_cls in profile.enrolled_classroom_ids:
            where_filter = {"classroom_id": {"$eq": target_cls}}
            reasoning_msg = f"Searching in your classroom materials..."
        elif profile.enrolled_classroom_ids:
            where_filter = {"classroom_id": {"$in": profile.enrolled_classroom_ids}}
            reasoning_msg = f"Searching across {len(profile.enrolled_classroom_ids)} classrooms..."
        else:
            logger.warning("[retriever_node] No enrolled classrooms for user")
            return {
                "retrieved_chunks": [],
                "used_sources": [],
                "no_chunks_found": True,
                "processing_status": "generating",
                "reasoning": state.get("reasoning", []) + ["No enrolled classrooms found."],
            }

    logger.info("[retriever_node] filter=%s", where_filter)

    # ── Query ChromaDB ────────────────────────────────────────────
    try:
        results = await asyncio.to_thread(
            collection.query,
            query_embeddings=[state["query_embedding"]],
            n_results=8,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # Fallback: if scoped search yielded 0, expand to all enrolled
        if (not results.get("documents") or not results["documents"][0]) \
                and scope.scope_classroom_id and profile.enrolled_classroom_ids:
            logger.info("[retriever_node] Scoped search empty — expanding to all classrooms")
            where_filter = {"classroom_id": {"$in": profile.enrolled_classroom_ids}}
            results = await asyncio.to_thread(
                collection.query,
                query_embeddings=[state["query_embedding"]],
                n_results=8,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
    except Exception as e:
        logger.error("[retriever_node] ChromaDB query failed: %s", e)
        return {
            "retrieved_chunks": [],
            "used_sources": [],
            "recent_files_context": recent_files,
            "no_chunks_found": True,
            "processing_status": "generating",
        }

    # ── Parse + apply relevance threshold ────────────────────────
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    retrieved_chunks: list[RetrievedChunk] = []
    used_sources: list[dict] = []

    for doc, meta, dist in zip(documents, metadatas, distances):
        score = round(1 - dist, 4)

        # Hard relevance gate — low-scoring chunks are NOT passed to synthesis
        if score < RELEVANCE_THRESHOLD:
            logger.debug("[retriever_node] Dropping chunk score=%.4f file=%s",
                         score, meta.get("file_name", "?"))
            continue

        chunk = RetrievedChunk(
            text=doc,
            source_file=meta.get("file_name", "Unknown"),
            file_type=meta.get("file_type", "unknown"),
            page_number=meta.get("page_number"),
            timestamp_start=meta.get("timestamp_start"),
            timestamp_end=meta.get("timestamp_end"),
            subject=meta.get("subject"),
            relevance_score=score,
        )
        retrieved_chunks.append(chunk)
        used_sources.append({
            "file_name": chunk.source_file,
            "file_type": chunk.file_type,
            "page_number": chunk.page_number,
            "timestamp_start": chunk.timestamp_start,
            "timestamp_end": chunk.timestamp_end,
            "relevance_score": score,
        })

    no_chunks = len(retrieved_chunks) == 0

    if no_chunks:
        logger.info("[retriever_node] No chunks passed threshold — flagging no_chunks_found")
    else:
        logger.info("[retriever_node] %d chunks passed threshold (top=%.4f)",
                    len(retrieved_chunks), retrieved_chunks[0].relevance_score)

    return {
        "retrieved_chunks": retrieved_chunks,
        "used_sources": used_sources,        # Only threshold-passing chunks
        "no_chunks_found": no_chunks,
        "processing_status": "generating",
        "reasoning": state.get("reasoning", []) + [
            reasoning_msg,
            f"Found {len(retrieved_chunks)} relevant sections." if not no_chunks
            else "No matching content found in your course materials.",
        ],
    }


# ══════════════════════════════════════════════════════════════════════
# NODE 5B: web_search_node
# Real-time search using DuckDuckGo for WEB_SEARCH intent.
# ══════════════════════════════════════════════════════════════════════

async def web_search_node(state: dict) -> dict:
    """Fetch top 5 snippets from DuckDuckGo."""
    logger.info("[web_search_node] Searching for: %s", state["query"][:60])

    try:
        from ddgs import DDGS

        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(state["query"], max_results=5))

        results = await asyncio.to_thread(_search)

        processed = [
            {"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")}
            for r in results
        ]
        logger.info("[web_search_node] %d results returned", len(processed))
        return {
            "web_search_results": processed,
            "used_sources": [],  # Web sources are handled separately in synthesis prompt
            "processing_status": "generating",
            "reasoning": state.get("reasoning", []) + [
                f"Found {len(processed)} recent web results."
            ],
        }
    except ImportError:
        logger.error("[web_search_node] duckduckgo-search not installed. Run: uv add duckduckgo-search")
        return {
            "web_search_results": [],
            "used_sources": [],
            "error": "Web search unavailable. Install duckduckgo-search.",
            "processing_status": "generating",
        }
    except Exception as e:
        logger.error("[web_search_node] Search failed: %s", e)
        return {
            "web_search_results": [],
            "used_sources": [],
            "error": f"Search failed: {e}",
            "processing_status": "generating",
        }


# ══════════════════════════════════════════════════════════════════════
# NODE 6: synthesis_node_stream (async generator — NOT in the graph)
# Driven by the SSE endpoint after the graph has completed state.
# Yields individual tokens for real-time streaming to the client.
# ══════════════════════════════════════════════════════════════════════

SYNTHESIS_SYSTEM_PROMPT = r"""\
You are CampusAI, a focused academic tutor for engineering and technology students.

## CORE RULES (NON-NEGOTIABLE)

1. **Answer priority order:**
   - **Course material found:** Base your answer primarily on the provided RELEVANT COURSE MATERIAL. You may supplement with general academic/technical knowledge to clarify or extend the concepts.
   - **No course material found, but question is ACADEMIC or TECHNICAL:** Answer confidently from your broad academic knowledge (computer science, engineering, mathematics, science, technology, system design, etc.). Clearly note that the answer is from general knowledge, not from their uploaded materials.
   - **No course material found and question is NOT academic/technical:** Politely decline and redirect the student to ask something academic.
   - **Web results provided:** Summarize them with proper clickable source citations.

2. **What counts as academic/technical:** System design, algorithms, data structures, networks, operating systems, software engineering, mathematics, physics, chemistry, any STEM or computer science topic. When in doubt, answer it.

3. **What to refuse:** Entertainment, sports, celebrity news, politics, unrelated personal advice, writing assignments for the student, solving their exam problems verbatim.

4. **NEVER hallucinate sources.** Only cite a course file if its content appears in the RELEVANT COURSE MATERIAL section.

5. **ACADEMIC INTEGRITY:** Never write assignments, solve exam problems, or provide direct exam answers. Explain concepts and approaches only.

## CITATION FORMAT
- Course PDF: "According to **[filename, Page X]**..."
- Course Video: "As explained in **[filename]** at [timestamp]..."
- Web source: Use a clickable markdown link → [Source Title](URL)
- General knowledge (no source): State "Based on general academic knowledge..."

## MATHEMATICS & TABLES
- **STRICT LaTeX MATH**: Use `$...$` for inline math and `$$ ... $$` for block equations. Every single mathematical symbol, variable ($x$, $y$, $\eta$, etc.), and equation MUST be wrapped in LaTeX.
- **CLEAN TABLES**: Use standard markdown table syntax. Ensure headers are clear and columns are aligned. Do not use complex HTML tables.

## RESPONSE STYLE
- **HEADER STYLE**: Never use `###` or plain numbered lists for section titles. EVERY section must start with a `**Bold Header**` on its own line.
- **SPACING**: Use a double newline (two blank lines) between major sections to ensure the response is airy and readable.
- **BULLETS**: Use `- Bullet points` for details within sections.
- **SUMMARY FORMAT**:
  **Section Title**
  - Detail/Point 1
  - Detail/Point 2

  **Next Section Title**
  - Detail/Point 1
- Use code blocks where appropriate.
- End with a relevant follow-up question to guide the student.
- Keep tone encouraging but precise.
"""


async def synthesis_node_stream(state: dict) -> AsyncGenerator[str, None]:
    """
    Stream response tokens. Called from the SSE layer after graph completion.
    Receives the full state with retrieved_chunks and/or web_search_results.
    """
    prompt_parts = _build_synthesis_prompt(state)

    last_error = None
    for model_name in CHAT_MODEL_CHAIN:
        attempts = max(len(chat_key_manager.keys), 1)
        for _ in range(attempts):
            client, key = chat_key_manager.get_client()
            try:
                stream = await client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=prompt_parts,
                    config=types.GenerateContentConfig(
                        system_instruction=SYNTHESIS_SYSTEM_PROMPT,
                        temperature=0.3,
                        max_output_tokens=2048,
                    ),
                )
                async for chunk in stream:
                    if chunk.text:
                        yield chunk.text
                return  # Success
            except Exception as e:
                last_error = e
                err_msg = str(e)
                if "503" in err_msg or "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    chat_key_manager.mark_unhealthy(key)
                    continue
                else:
                    break

    logger.error("[synthesis_node_stream] All models failed: %s", last_error)
    yield "I'm having trouble generating a response right now. Please try again in a moment."


def _build_synthesis_prompt(state: dict) -> str:
    """Assemble the final prompt from state. Only includes genuine context."""
    parts: list[str] = []

    # Classroom framing
    ctx = state.get("classroom_context") or {}
    if ctx:
        parts.append(f"CLASSROOM: {ctx.get('name')} | Subject: {ctx.get('subject')}")
        if ctx.get("description"):
            parts.append(f"DESCRIPTION: {ctx.get('description')}")

    # Recent files context (Metadata about latest uploads)
    recent_files = state.get("recent_files_context", [])
    if recent_files:
        ctx_str = "\nMOST RECENT UPLOADS IN THIS CLASSROOM:\n"
        for f in recent_files:
            ctx_str += f"- {f['original_name']} (Uploaded: {f.get('uploaded_at', 'unknown')})\n"
        parts.append(ctx_str)

    # Conversation history
    if state.get("chat_history"):
        history_text = "CONVERSATION HISTORY:\n"
        for msg in state["chat_history"]:
            history_text += f"{msg.role.upper()}: {msg.content}\n"
        parts.append(history_text)

    # RAG chunks (only threshold-passing chunks are in retrieved_chunks)
    chunks = state.get("retrieved_chunks", [])
    no_chunks = state.get("no_chunks_found", False)

    if chunks:
        context = "\nRELEVANT COURSE MATERIAL:\n" + "─" * 50 + "\n"
        for i, c in enumerate(chunks, 1):
            if c.file_type == "video" and c.timestamp_start:
                cite = f"[{c.source_file} | {c.timestamp_start}-{c.timestamp_end}]"
            elif c.file_type == "pdf" and c.page_number:
                cite = f"[{c.source_file} | Page {c.page_number}]"
            else:
                cite = f"[{c.source_file}]"
            context += f"\nSOURCE {i} {cite}:\n{c.text}\n" + "─" * 50 + "\n"
        parts.append(context)
    elif no_chunks:
        # No relevant course material found — allow general academic/tech knowledge
        parts.append(
            "\nNOTE: No relevant course material was found in the student's uploaded files for this query. "
            "If the question is academic or technical in nature (e.g. system design, algorithms, programming, "
            "engineering, science, mathematics), answer it from your broad academic knowledge and clearly state "
            "'This is based on general academic knowledge, not your uploaded course materials.' "
            "If the question is NOT academic or technical, politely decline and ask them to ask something academic.\n"
        )

    # Web search results
    web_results = state.get("web_search_results", [])
    if web_results:
        context = "\nRECENT WEB INFORMATION:\n" + "─" * 50 + "\n"
        for i, r in enumerate(web_results, 1):
            context += (
                f"\nSOURCE {i}:\n"
                f"Title: {r['title']}\n"
                f"URL: {r['href']}\n"
                f"Summary: {r['body']}\n"
                + "─" * 50 + "\n"
            )
        context += (
            "\nIMPORTANT: When citing these web sources in your response, "
            "format each citation as a clickable markdown link: [Source Title](URL)\n"
        )
        parts.append(context)

    parts.append(f"\nSTUDENT QUESTION: {state['query']}")

    return "\n".join(parts)
