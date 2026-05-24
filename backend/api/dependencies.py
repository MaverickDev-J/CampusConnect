"""FastAPI dependencies – auth, role checks, classroom membership."""

import json
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.security import decode_access_token
from database.mongo import get_db
from database.redis import get_redis

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_USER_CACHE_TTL = 300  # 5 minutes


async def get_current_user(token: str = Depends(oauth2_scheme)):
    return await get_user_from_token(token)


async def get_user_from_token(token: str) -> dict:
    """
    Decode the bearer token and fetch the user.
    
    Uses Redis to cache user profiles for 5 minutes to avoid hitting
    MongoDB on every single authenticated request.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    # ── Redis cache lookup (avoids MongoDB hit on every request) ───
    cache_key = f"user_cache:{user_id}"
    try:
        redis = await get_redis()
        cached_raw = await redis.get(cache_key)
        if cached_raw:
            return json.loads(cached_raw)
    except Exception as e:
        logger.warning("[get_current_user] Redis cache miss/error: %s", e)

    # ── MongoDB fallback ────────────────────────────────────────────
    db = get_db()
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise credentials_exception

    user["_id"] = str(user["_id"])  # ObjectId → str for JSON serialization

    # ── Write back to Redis cache ──────────────────────────────────
    try:
        redis = await get_redis()
        await redis.setex(cache_key, _USER_CACHE_TTL, json.dumps(user, default=str))
    except Exception as e:
        logger.warning("[get_current_user] Failed to cache user in Redis: %s", e)

    return user


def invalidate_user_cache(user_id: str):
    """
    Helper to call when user data changes (password change, role update).
    Schedules Redis key deletion so the next request fetches fresh data.
    """
    import asyncio

    async def _delete():
        try:
            redis = await get_redis()
            await redis.delete(f"user_cache:{user_id}")
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_delete())
    except Exception:
        pass


# ── Role-based access control ──────────────────────────────────────

def require_role(*allowed_roles: str):
    """
    Dependency factory that enforces role-based access.

    Usage::

        @router.post("/endpoint")
        async def my_endpoint(
            current_user: dict = Depends(require_role("superadmin", "teacher")),
        ):
            ...
    """
    async def _check(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
        return current_user

    return _check


# ── Classroom helpers ──────────────────────────────────────────────

async def get_classroom_or_404(classroom_id: str) -> dict:
    """Fetch a classroom by ID or raise 404."""
    db = get_db()
    classroom = await db.classrooms.find_one({"classroom_id": classroom_id})
    if not classroom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Classroom {classroom_id} not found",
        )
    return classroom


async def require_classroom_member(classroom_id: str, user_id: str) -> dict:
    """Raise 403 if the user is not a member of the classroom."""
    classroom = await get_classroom_or_404(classroom_id)
    member_ids = [m["user_id"] for m in classroom.get("members", [])]
    if user_id not in member_ids and classroom.get("created_by") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this classroom",
        )
    return classroom
