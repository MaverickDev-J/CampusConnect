"""Demo router — frictionless guest login for interviewers.

POST /api/auth/demo-login
    - Idempotently seeds: demo teacher, demo student, classroom,
      file metadata, ChromaDB vectors, announcement, calendar event.
    - Returns a JWT for the demo guest student.
    - Safe to call repeatedly (all inserts are guarded by existence checks).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from core.security import hash_password, create_access_token
from database.mongo import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Demo"])

# ── Constants ──────────────────────────────────────────────────────

DEMO_TEACHER_ID = "tea_demo_prof"
DEMO_TEACHER_EMAIL = "demo.prof@campusconnect.dev"

DEMO_GUEST_ID = "stu_demo_guest"
DEMO_GUEST_EMAIL = "demo.guest@campusconnect.dev"

DEMO_CLASSROOM_ID = "cls_demo_sandbox"
DEMO_FILE_ID = "file_demo_architecture"

# ── Architecture content chunks (what the AI will know about) ──────

ARCHITECTURE_CHUNKS = [
    {
        "id": f"{DEMO_FILE_ID}_c1",
        "text": (
            "CampusConnect System Overview\n\n"
            "CampusConnect is a multi-agent AI-powered classroom platform built with a modern "
            "distributed architecture. The backend is powered by FastAPI (Python) for async HTTP/WebSocket "
            "handling, with Celery for background task processing. The frontend is a Next.js 15 React "
            "application using the App Router with server components and Framer Motion animations.\n\n"
            "The complete request flow: A student asks a question in the chat UI → the frontend sends "
            "the query via HTTP POST → FastAPI receives it and runs it through a 6-node LangGraph agent "
            "pipeline → the agent retrieves relevant document chunks from ChromaDB → synthesizes an answer "
            "using Gemini LLM → streams the response back token-by-token via Server-Sent Events.\n\n"
            "Key infrastructure: MongoDB (document store), Redis (cache + broker + PubSub), "
            "ChromaDB (vector embeddings), Celery (async task queue), Nginx (reverse proxy in production)."
        ),
    },
    {
        "id": f"{DEMO_FILE_ID}_c2",
        "text": (
            "LangGraph Multi-Agent Pipeline\n\n"
            "The AI chat system uses LangGraph to orchestrate a 6-node agentic graph that processes "
            "every student query through a structured decision pipeline:\n\n"
            "Node 1 — Router Node: Classifies the query intent using Gemini Flash Lite (fastest model). "
            "Determines if the query needs document retrieval, web search, or is a general question.\n\n"
            "Node 2 — Classifier Node: Analyzes query complexity and determines the retrieval strategy. "
            "Routes to vector search, keyword search, or both.\n\n"
            "Node 3 — Retriever Node: Performs semantic search against ChromaDB using cosine similarity. "
            "Returns top-8 chunks filtered by a 0.35 relevance threshold.\n\n"
            "Node 4 — Web Search Node: For queries requiring current information, performs web search "
            "using Tavily API as a fallback knowledge source.\n\n"
            "Node 5 — Synthesis Node: Generates the final answer using Gemini 2.5 Flash with retrieved "
            "context. Supports per-token streaming via async generators (LangGraph doesn't natively "
            "support streaming inside nodes, so synthesis runs outside the graph).\n\n"
            "Node 6 — Guardrail Node: Post-processing safety check. Ensures responses are relevant, "
            "factual, and appropriate for an educational context."
        ),
    },
    {
        "id": f"{DEMO_FILE_ID}_c3",
        "text": (
            "3-Tier PDF Extraction Pipeline\n\n"
            "CampusConnect uses a tiered extraction strategy to maximize document understanding quality "
            "while ensuring every file gets processed:\n\n"
            "Tier 1 — Gemini File API (Best Quality): Uploads the PDF to Gemini's multimodal File API. "
            "The model can understand tables, diagrams, equations, scanned text, and complex layouts. "
            "Uses the INGESTION key pool with automatic retry and key rotation on 429 errors. "
            "Typical latency: 10-90 seconds.\n\n"
            "Tier 2 — Docling (Good Quality, Free): Falls back to Docling, an open-source document "
            "understanding library that runs locally. Handles structured text and basic tables without "
            "any API key. CPU-based, typical latency: 30-120 seconds.\n\n"
            "Tier 3 — PyMuPDF (Text Only, Fastest): Last resort fallback using PyMuPDF for raw text "
            "extraction. No table, image, or equation understanding. Files processed with this tier "
            "are flagged in the UI so students know the content may be incomplete.\n\n"
            "After extraction, text is chunked (800 chars, 100 overlap) using LangChain's "
            "RecursiveCharacterTextSplitter, then embedded via Gemini Embedding 001 in batches of 50."
        ),
    },
    {
        "id": f"{DEMO_FILE_ID}_c4",
        "text": (
            "Redis Architecture — 4 Roles in One Service\n\n"
            "Redis serves four distinct roles in CampusConnect, which is why it was chosen over "
            "RabbitMQ (which would only cover the broker role):\n\n"
            "Role 1 — Celery Broker: Redis acts as the message broker for Celery background tasks. "
            "When a PDF is uploaded, FastAPI enqueues an ingestion task that Redis delivers to the "
            "Celery worker. Also serves as the result backend.\n\n"
            "Role 2 — User Profile Cache: Authenticated user profiles are cached in Redis with a "
            "5-minute TTL. This prevents hitting MongoDB on every single authenticated API request. "
            "The cache is invalidated on password change or profile update.\n\n"
            "Role 3 — WebSocket PubSub: Redis PubSub enables real-time notifications across multiple "
            "FastAPI workers. When a Celery worker finishes processing a PDF, it publishes a message "
            "to Redis, which fans out to all connected WebSocket clients in that classroom.\n\n"
            "Role 4 — Semantic Cache: Query-response pairs are cached with their embedding vectors. "
            "New queries are compared using cosine similarity (threshold 0.93). Cache hits return "
            "responses in under 10ms instead of 2-5 seconds for a full LangGraph pipeline run. "
            "Each classroom has its own cache namespace with a 24-hour TTL and max 200 entries."
        ),
    },
    {
        "id": f"{DEMO_FILE_ID}_c5",
        "text": (
            "Database Design — MongoDB + ChromaDB\n\n"
            "CampusConnect uses a polyglot persistence strategy with two databases:\n\n"
            "MongoDB (Document Store): Stores all application data — users (with bcrypt-hashed "
            "passwords), classrooms (with embedded member arrays), chat sessions and history, "
            "file metadata (with processing status tracking), announcements, notifications, and "
            "calendar events. Indexes are created on startup for all query patterns (email lookups, "
            "classroom membership queries, pagination sorts).\n\n"
            "ChromaDB (Vector Store): Stores document embeddings for semantic search. Runs as a "
            "Docker service in HTTP server mode (not embedded mode). The old CampusMind project used "
            "ChromaDB's PersistentClient which caused file-locking conflicts between FastAPI and "
            "Celery workers accessing the same SQLite file. Server mode (HttpClient) completely "
            "eliminates this issue.\n\n"
            "Why not pgvector? Adding PostgreSQL alongside MongoDB would mean maintaining two "
            "relational databases. ChromaDB is purpose-built for vector search with HNSW indexing "
            "and cosine similarity, and its Docker image is lightweight (~200MB).\n\n"
            "Connection Management: MongoDB and ChromaDB connections are initialized once on Celery "
            "worker startup via worker_init signals, not per-task. This prevents connection churn "
            "and reduces latency on every ingestion task."
        ),
    },
]


# ── Endpoint ───────────────────────────────────────────────────────

@router.post("/api/auth/demo-login")
async def demo_login():
    """
    Frictionless demo login for interviewers.

    Creates a pre-seeded environment on first call, then returns JWT instantly.
    Idempotent — safe to call repeatedly.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    try:
        # ── 0. Clean up previous demo sessions (fresh slate) ──────
        old_sessions = await db.chat_sessions.find(
            {"user_id": DEMO_GUEST_ID}, {"session_id": 1}
        ).to_list(length=500)
        old_sids = [s["session_id"] for s in old_sessions]
        if old_sids:
            await db.chat_history.delete_many({"session_id": {"$in": old_sids}})
            await db.chat_sessions.delete_many({"user_id": DEMO_GUEST_ID})
            logger.info("[demo] Cleaned up %d old demo sessions", len(old_sids))
        # ── 1. Ensure Demo Teacher exists ─────────────────────────
        if not await db.users.find_one({"user_id": DEMO_TEACHER_ID}):
            await db.users.insert_one({
                "user_id": DEMO_TEACHER_ID,
                "email": DEMO_TEACHER_EMAIL,
                "name": "Prof. Demo",
                "password": hash_password(uuid4().hex),
                "role": "teacher",
                "profile": {"department": "Computer Science"},
            })
            logger.info("[demo] Created demo teacher: %s", DEMO_TEACHER_ID)

        # ── 2. Ensure Demo Guest Student exists ───────────────────
        if not await db.users.find_one({"user_id": DEMO_GUEST_ID}):
            await db.users.insert_one({
                "user_id": DEMO_GUEST_ID,
                "email": DEMO_GUEST_EMAIL,
                "name": "Demo Guest",
                "password": hash_password(uuid4().hex),
                "role": "student",
                "profile": {"roll_no": "DEMO001"},
            })
            logger.info("[demo] Created demo guest: %s", DEMO_GUEST_ID)

        # ── 3. Ensure Demo Classroom exists ───────────────────────
        if not await db.classrooms.find_one({"classroom_id": DEMO_CLASSROOM_ID}):
            await db.classrooms.insert_one({
                "classroom_id": DEMO_CLASSROOM_ID,
                "name": "CampusConnect — System Architecture",
                "description": (
                    "Interactive AI sandbox pre-loaded with CampusConnect's own architecture docs. "
                    "Ask about Redis caching, LangGraph pipelines, 3-tier PDF extraction, "
                    "or upload your own documents!"
                ),
                "subject": "Computer Science & AI",
                "join_code": "DEMO01",
                "created_by": DEMO_TEACHER_ID,
                "members": [
                    {"user_id": DEMO_TEACHER_ID, "role": "teacher", "joined_at": now},
                    {"user_id": DEMO_GUEST_ID, "role": "student", "joined_at": now},
                ],
                "created_at": now,
                "updated_at": now,
            })
            logger.info("[demo] Created demo classroom: %s", DEMO_CLASSROOM_ID)

        # ── 4. Ensure Demo File Metadata exists ───────────────────
        if not await db.file_metadata.find_one({"file_id": DEMO_FILE_ID}):
            await db.file_metadata.insert_one({
                "file_id": DEMO_FILE_ID,
                "classroom_id": DEMO_CLASSROOM_ID,
                "original_name": "CampusConnect_Architecture_Guide.pdf",
                "file_type": "pdf",
                "uploaded_by": DEMO_TEACHER_ID,
                "uploaded_at": now,
                "size_bytes": 45000,
                "sha256_hash": f"demo_{uuid4().hex}",
                "storage_path": None,
                "processing": {
                    "status": "completed",
                    "chunk_count": len(ARCHITECTURE_CHUNKS),
                    "extraction_method": "gemini_file_api",
                    "error": None,
                },
            })
            logger.info("[demo] Created demo file metadata: %s", DEMO_FILE_ID)

        # ── 5. Seed ChromaDB Vectors ──────────────────────────────
        try:
            from database.chroma import get_chroma_collection

            collection = get_chroma_collection()
            if collection is None:
                raise RuntimeError("ChromaDB collection not initialized")

            # Check if vectors already exist
            existing = collection.get(
                ids=[ARCHITECTURE_CHUNKS[0]["id"]],
                include=[],
            )
            if not existing or not existing.get("ids") or len(existing["ids"]) == 0:
                # Embed the chunks using Gemini
                from core.llm_router import chat_key_manager

                client, _key = chat_key_manager.get_client()

                chunk_texts = [c["text"] for c in ARCHITECTURE_CHUNKS]
                chunk_ids = [c["id"] for c in ARCHITECTURE_CHUNKS]

                resp = await client.aio.models.embed_content(
                    model="models/gemini-embedding-001",
                    contents=chunk_texts,
                    config={"task_type": "RETRIEVAL_DOCUMENT"},
                )

                embeddings = [list(emb.values) for emb in resp.embeddings]

                metadatas = [
                    {
                        "file_id": DEMO_FILE_ID,
                        "file_name": "CampusConnect_Architecture_Guide.pdf",
                        "file_type": "pdf",
                        "classroom_id": DEMO_CLASSROOM_ID,
                        "doc_type": "material",
                        "uploaded_by": DEMO_TEACHER_ID,
                        "extraction_method": "gemini_file_api",
                    }
                    for _ in ARCHITECTURE_CHUNKS
                ]

                collection.upsert(
                    ids=chunk_ids,
                    documents=chunk_texts,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                logger.info("[demo] Seeded %d vectors in ChromaDB", len(chunk_ids))
            else:
                logger.debug("[demo] ChromaDB vectors already exist, skipping")

        except Exception as e:
            # Non-fatal: demo login still works, just no pre-loaded chat context
            logger.warning("[demo] Vector seeding failed (non-fatal): %s", e)

        # ── 6. Seed Welcome Announcement ──────────────────────────
        if not await db.announcements.find_one({"announcement_id": "ann_demo_welcome"}):
            await db.announcements.insert_one({
                "announcement_id": "ann_demo_welcome",
                "classroom_id": DEMO_CLASSROOM_ID,
                "author_id": DEMO_TEACHER_ID,
                "author_name": "Prof. Demo",
                "author_role": "teacher",
                "content": (
                    "Welcome to the CampusConnect AI Sandbox! 🎓\n\n"
                    "This classroom is pre-loaded with documentation about CampusConnect's "
                    "system architecture. Try asking:\n"
                    "• \"How does the semantic cache work?\"\n"
                    "• \"Explain the 3-tier PDF extraction pipeline\"\n"
                    "• \"Why was Redis chosen over RabbitMQ?\"\n\n"
                    "You can also upload your own PDF to see real-time ingestion in action!"
                ),
                "file_id": None,
                "created_at": now,
            })
            logger.info("[demo] Created welcome announcement")

        # ── 7. Seed Calendar Event ────────────────────────────────
        if not await db.calendar_events.find_one({"event_id": "evt_demo_review"}):
            await db.calendar_events.insert_one({
                "event_id": "evt_demo_review",
                "classroom_id": DEMO_CLASSROOM_ID,
                "title": "Architecture Deep Dive",
                "description": (
                    "Review session covering LangGraph pipeline, Redis caching strategy, "
                    "and 3-tier PDF extraction"
                ),
                "date": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
                "type": "event",
                "created_by": DEMO_TEACHER_ID,
                "created_at": now,
            })
            logger.info("[demo] Created demo calendar event")

        # ── 8. Sign JWT ───────────────────────────────────────────
        token = create_access_token({
            "user_id": DEMO_GUEST_ID,
            "role": "student",
        })

        logger.info("[demo] Demo login successful for %s", DEMO_GUEST_ID)
        return {"access_token": token, "token_type": "bearer"}

    except Exception as e:
        logger.exception("[demo] Demo login failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Demo setup failed: {str(e)[:200]}")
