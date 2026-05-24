"""CampusMind FastAPI application entry-point."""

import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.security import hash_password
from database.mongo import connect_db, close_db, get_db
from database.chroma import connect_chroma
from database.redis import get_redis
from core.websocket import manager
import asyncio

logger = logging.getLogger(__name__)


# ── Super-admin auto-seed ────────────────────────────────────────────

async def _seed_superadmin() -> None:
    """Create the superadmin user if it doesn't exist yet."""
    db = get_db()
    existing = await db.users.find_one({"role": "superadmin"})
    if existing:
        logger.info("[SEED] Superadmin already exists: %s", existing["email"])
        return

    user_id = f"adm_{uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": settings.SUPERADMIN_EMAIL,
        "name": "Superadmin",
        "password": hash_password(settings.SUPERADMIN_PASSWORD),
        "role": "superadmin",
        "profile": {},
    }
    await db.users.insert_one(user_doc)
    logger.info("[SEED] Superadmin created: %s (user_id=%s)", settings.SUPERADMIN_EMAIL, user_id)


# ── Lifespan ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 0. Startup guard: reject insecure defaults ─────────────────
    _INSECURE_SECRETS = {
        "super-secret-change-me",
        "super-secret-key-change-this-in-production",
        "changeme",
        "",
    }
    if settings.JWT_SECRET in _INSECURE_SECRETS or len(settings.JWT_SECRET) < 32:
        raise RuntimeError(
            "FATAL: JWT_SECRET is missing or insecure. "
            "Generate a strong 32+ char secret: openssl rand -hex 32"
        )

    # ── 1. Connect MongoDB ─────────────────────────────────────────
    await connect_db()
    db = get_db()

    # ── 2. Ensure all indexes ──────────────────────────────────────
    # Users
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)

    # Classrooms
    await db.classrooms.create_index("classroom_id", unique=True)
    await db.classrooms.create_index("join_code", unique=True)
    await db.classrooms.create_index("members.user_id")          # For classroom listing by user

    # Files
    await db.file_metadata.create_index("sha256_hash", unique=True)
    await db.file_metadata.create_index("file_id", unique=True)
    await db.file_metadata.create_index([("classroom_id", 1), ("uploaded_at", -1)])
    await db.file_metadata.create_index("processing.status")

    # Chat
    await db.chat_sessions.create_index("session_id", unique=True)
    await db.chat_sessions.create_index([("user_id", 1), ("updated_at", -1)])
    await db.chat_sessions.create_index([("classroom_id", 1), ("updated_at", -1)])
    await db.chat_history.create_index([("session_id", 1), ("timestamp", 1)])

    # Announcements
    await db.announcements.create_index("announcement_id", unique=True)
    await db.announcements.create_index([("classroom_id", 1), ("created_at", -1)])

    # Notifications
    await db.notifications.create_index([("user_id", 1), ("is_read", 1), ("created_at", -1)])

    # Calendar
    await db.calendar_events.create_index([("classroom_id", 1), ("date", 1)])

    print("[OK] MongoDB connected & all indexes ensured")

    # ── 3. Connect ChromaDB ────────────────────────────────────────
    connect_chroma()
    print("[OK] ChromaDB connected (campus_vectors collection ready)")

    # ── 4. Start WebSocket Redis listener ─────────────────────────
    asyncio.create_task(manager.listen_to_redis())

    # ── 5. Seed superadmin ─────────────────────────────────────────
    await _seed_superadmin()

    yield

    # ── Shutdown ───────────────────────────────────────────────────
    await close_db()
    print("[STOP] MongoDB connection closed")


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="CampusMind API",
    description="Smart Campus AI Knowledge Base",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────
# Explicit origins — never use ["*"] with allow_credentials=True
# (browsers reject it, and it's insecure)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ─────────────────────────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    print("[OK] Rate limiting enabled")
except ImportError:
    print("[WARN] slowapi not installed — rate limiting disabled. Run: uv add slowapi")
    limiter = None

# ── Routers ─────────────────────────────────────────────────────────

from api.routers import (
    auth,
    classroom,
    announcements,
    upload,
    chat,
    superadmin,
    calendar,
    notifications,
)

app.include_router(auth.router)
app.include_router(superadmin.router)
app.include_router(classroom.router)
app.include_router(upload.router)
app.include_router(upload.files_router)
app.include_router(chat.router)
app.include_router(announcements.router)
app.include_router(calendar.router)
app.include_router(notifications.router)

# ── Static files ─────────────────────────────────────────────────────
# NOTE: For production, serve these via nginx or a CDN instead.
app.mount("/static", StaticFiles(directory="storage/uploads"), name="static")


# ── WebSocket Hub ────────────────────────────────────────────────────

WS_HEARTBEAT_TIMEOUT = 60  # seconds — close stale connections

@app.websocket("/ws/classroom/{classroom_id}")
async def classroom_websocket_endpoint(
    websocket: WebSocket,
    classroom_id: str,
    token: str | None = None,  # ?token=<jwt> in query string
):
    """
    Classroom-scoped WebSocket for real-time updates.
    Requires a valid JWT token (passed as ?token=<jwt> query param).
    Implements a 60-second heartbeat — if no ping received, connection is closed.
    """
    from api.dependencies import get_user_from_token
    from database.mongo import get_db as _get_db

    # ── 1. Authenticate ────────────────────────────────────────────
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        logger.warning("[WS] Rejected unauthenticated connection for classroom %s", classroom_id)
        return

    try:
        user = await get_user_from_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        logger.warning("[WS] Rejected invalid token for classroom %s", classroom_id)
        return

    # ── 2. Verify classroom membership ──────────────────────────────
    if user.get("role") != "superadmin":
        db = _get_db()
        classroom = await db.classrooms.find_one({"classroom_id": classroom_id})
        if not classroom:
            await websocket.close(code=4004, reason="Classroom not found")
            return
        member_ids = [m["user_id"] for m in classroom.get("members", [])]
        if user["user_id"] not in member_ids:
            await websocket.close(code=4003, reason="Not a classroom member")
            logger.warning(
                "[WS] Rejected non-member %s for classroom %s",
                user["user_id"], classroom_id,
            )
            return

    # ── 3. Accept and maintain connection ──────────────────────────
    logger.info("[WS] ✅ Accepted user=%s classroom=%s", user["user_id"], classroom_id)
    try:
        await manager.connect(websocket, classroom_id)
    except Exception as e:
        logger.error("[WS] Handshake failed: %s", e)
        return

    try:
        while True:
            # Wait for a message with timeout — acts as heartbeat check
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_HEARTBEAT_TIMEOUT,
                )
                # Echo pings back as pongs (keep-alive)
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # No message received within timeout — close stale connection
                logger.info(
                    "[WS] Closing stale connection: user=%s classroom=%s",
                    user["user_id"], classroom_id,
                )
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[WS] Error for user=%s classroom=%s: %s", user["user_id"], classroom_id, e)
    finally:
        manager.disconnect(websocket, classroom_id)


# ── Health check ─────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Comprehensive health check. Verifies MongoDB, Redis, and ChromaDB.
    Returns 200 if all healthy, 200 with status='degraded' if partial.
    """
    checks: dict = {}

    # MongoDB
    db = get_db()
    try:
        await db.command("ping")
        checks["mongodb"] = "ok"
    except Exception as e:
        checks["mongodb"] = f"error: {str(e)[:100]}"

    # Redis
    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:100]}"

    # ChromaDB
    try:
        from database.chroma import get_chroma_collection
        col = get_chroma_collection()
        _ = col.count()
        checks["chromadb"] = "ok"
    except Exception as e:
        checks["chromadb"] = f"error: {str(e)[:100]}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
