"""Classroom router – create, list, join, detail, delete."""

import logging
import os
import string
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user, require_role
from database.mongo import get_db
from models.schemas import ClassroomCreate, ClassroomResponse, JoinClassroomBody

router = APIRouter(prefix="/api/classrooms", tags=["Classrooms"])
logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────

def _generate_join_code(length: int = 6) -> str:
    """Generate a random uppercase alphanumeric join code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _classroom_to_response(doc: dict, creator_name: str = None) -> ClassroomResponse:
    """Convert a MongoDB classroom document to a response model."""
    return ClassroomResponse(
        classroom_id=doc["classroom_id"],
        name=doc["name"],
        description=doc.get("description"),
        subject=doc.get("subject"),
        join_code=doc["join_code"],
        member_count=len(doc.get("members", [])),
        created_by=doc["created_by"],
        created_by_name=creator_name,
        created_at=doc["created_at"].isoformat()
        if isinstance(doc["created_at"], datetime)
        else str(doc["created_at"]),
    )


# ── POST /api/classrooms ─────────────────────────────────────────────

@router.post("", response_model=ClassroomResponse, status_code=status.HTTP_201_CREATED)
async def create_classroom(
    body: ClassroomCreate,
    current_user: dict = Depends(require_role("teacher", "superadmin")),
):
    """Create a new classroom. Teachers and Superadmin only."""
    db = get_db()

    # Generate a unique join code (retry on collision)
    for _ in range(10):
        join_code = _generate_join_code()
        if not await db.classrooms.find_one({"join_code": join_code}):
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique join code")

    now = datetime.now(timezone.utc)
    classroom_id = f"cls_{uuid4().hex[:12]}"

    classroom_doc = {
        "classroom_id": classroom_id,
        "name": body.name,
        "description": body.description,
        "subject": body.subject,
        "join_code": join_code,
        "created_by": current_user["user_id"],
        "members": [
            {
                "user_id": current_user["user_id"],
                "role": current_user["role"],
                "joined_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }

    await db.classrooms.insert_one(classroom_doc)
    return _classroom_to_response(classroom_doc)


# ── GET /api/classrooms ──────────────────────────────────────────────

@router.get("")
async def list_classrooms(
    page: int = 1,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """
    List classrooms for the current user.
    - Teachers/Students: own classrooms only
    - Superadmin: all classrooms
    Supports pagination.
    """
    db = get_db()
    user_id = current_user["user_id"]
    role = current_user["role"]
    skip = (max(page, 1) - 1) * min(limit, 100)

    if role == "superadmin":
        query = {}
    else:
        query = {"members.user_id": user_id}

    total = await db.classrooms.count_documents(query)
    cursor = db.classrooms.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(min(limit, 100))
    docs = await cursor.to_list(length=min(limit, 100))

    # --- Batch-fetch creator names (Optimization) ---
    creator_ids = list(set(d["created_by"] for d in docs))
    creator_map = {}
    if creator_ids:
        creator_cursor = db.users.find({"user_id": {"$in": creator_ids}}, {"user_id": 1, "name": 1})
        creator_docs = await creator_cursor.to_list(length=len(creator_ids))
        creator_map = {u["user_id"]: u["name"] for u in creator_docs}

    classrooms = [_classroom_to_response(d, creator_map.get(d["created_by"])) for d in docs]
    return {"classrooms": classrooms, "count": len(classrooms), "total": total, "page": page}


# ── GET /api/classrooms/{classroom_id} ──────────────────────────────

@router.get("/{classroom_id}")
async def get_classroom(
    classroom_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get classroom detail including member list. Must be a member or superadmin."""
    db = get_db()
    doc = await db.classrooms.find_one({"classroom_id": classroom_id})

    if not doc:
        raise HTTPException(status_code=404, detail="Classroom not found")

    user_id = current_user["user_id"]
    role = current_user["role"]
    member_ids = [m["user_id"] for m in doc.get("members", [])]

    if role != "superadmin" and user_id not in member_ids:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    # ── Batch-fetch all member users in ONE query (fixes N+1) ──────
    user_map: dict = {}
    if member_ids:
        user_cursor = db.users.find(
            {"user_id": {"$in": member_ids}},
            {"_id": 0, "password": 0},
        )
        user_docs = await user_cursor.to_list(length=500)
        user_map = {u["user_id"]: u for u in user_docs}

    members = []
    for m in doc.get("members", []):
        u = user_map.get(m["user_id"], {})
        members.append({
            "user_id": m["user_id"],
            "role": m["role"],
            "name": u.get("name", "Unknown"),
            "email": u.get("email", ""),
            "joined_at": m["joined_at"].isoformat()
            if isinstance(m.get("joined_at"), datetime)
            else str(m.get("joined_at", "")),
        })

    # Fetch creator name specifically for the detail view
    creator_user = await db.users.find_one({"user_id": doc["created_by"]}, {"name": 1})
    creator_name = creator_user["name"] if creator_user else "Unknown"

    return {
        "classroom_id": doc["classroom_id"],
        "name": doc["name"],
        "description": doc.get("description"),
        "subject": doc.get("subject"),
        "join_code": doc["join_code"],
        "created_by": doc["created_by"],
        "created_by_name": creator_name,
        "members": members,
        "member_count": len(members),
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc["created_at"], datetime)
        else str(doc["created_at"]),
    }


# ── POST /api/classrooms/join ────────────────────────────────────────

@router.post("/join")
async def join_classroom(
    body: JoinClassroomBody,
    current_user: dict = Depends(get_current_user),
):
    """Join a classroom using a 6-character join code."""
    db = get_db()
    user_id = current_user["user_id"]
    join_code = body.join_code.upper().strip()

    classroom = await db.classrooms.find_one({"join_code": join_code})
    if not classroom:
        raise HTTPException(status_code=404, detail="Invalid join code")

    member_ids = [m["user_id"] for m in classroom.get("members", [])]
    if user_id in member_ids:
        return {
            "message": "Already a member of this classroom",
            "classroom_id": classroom["classroom_id"],
            "name": classroom["name"],
        }

    now = datetime.now(timezone.utc)
    await db.classrooms.update_one(
        {"classroom_id": classroom["classroom_id"]},
        {
            "$push": {
                "members": {
                    "user_id": user_id,
                    "role": current_user["role"],
                    "joined_at": now,
                }
            },
            "$set": {"updated_at": now},
        },
    )

    return {
        "message": "Successfully joined classroom",
        "classroom_id": classroom["classroom_id"],
        "name": classroom["name"],
        "join_code": classroom["join_code"],
    }


# ── DELETE /api/classrooms/{classroom_id} ───────────────────────────

@router.delete("/{classroom_id}", status_code=status.HTTP_200_OK)
async def delete_classroom(
    classroom_id: str,
    current_user: dict = Depends(require_role("teacher", "superadmin")),
):
    """
    Delete a classroom. Only the creator (teacher) or superadmin can delete.
    Cascade-deletes: files (disk + Chroma vectors), chat sessions, announcements, notifications.
    """
    db = get_db()

    classroom = await db.classrooms.find_one({"classroom_id": classroom_id})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    if (
        current_user["role"] != "superadmin"
        and classroom["created_by"] != current_user["user_id"]
    ):
        raise HTTPException(status_code=403, detail="Only the classroom creator can delete it")

    # ── Cascade 1: Files (disk + ChromaDB vectors + MongoDB metadata) ──
    try:
        from database.chroma import get_chroma_collection
        collection = get_chroma_collection()

        files_cursor = db.file_metadata.find({"classroom_id": classroom_id})
        files = await files_cursor.to_list(length=1000)

        for f in files:
            # Delete physical file from disk
            storage_path = f.get("storage_path")
            if storage_path and os.path.exists(storage_path):
                try:
                    os.remove(storage_path)
                except Exception as e:
                    logger.warning("[delete_classroom] Could not delete file %s: %s", storage_path, e)

            # Delete ChromaDB vectors for this file
            try:
                collection.delete(where={"file_id": f["file_id"]})
            except Exception as e:
                logger.warning("[delete_classroom] Could not delete Chroma vectors for %s: %s", f["file_id"], e)

        await db.file_metadata.delete_many({"classroom_id": classroom_id})
        logger.info("[delete_classroom] Deleted %d files for classroom %s", len(files), classroom_id)
    except Exception as e:
        logger.error("[delete_classroom] File cascade error: %s", e)

    # ── Cascade 2: Chat sessions + history ─────────────────────────
    try:
        sessions_cursor = db.chat_sessions.find(
            {"classroom_id": classroom_id}, {"session_id": 1}
        )
        sessions = await sessions_cursor.to_list(length=10000)
        session_ids = [s["session_id"] for s in sessions]

        if session_ids:
            await db.chat_history.delete_many({"session_id": {"$in": session_ids}})
        await db.chat_sessions.delete_many({"classroom_id": classroom_id})
        logger.info("[delete_classroom] Deleted %d chat sessions", len(session_ids))
    except Exception as e:
        logger.error("[delete_classroom] Chat cascade error: %s", e)

    # ── Cascade 3: Announcements ────────────────────────────────────
    try:
        await db.announcements.delete_many({"classroom_id": classroom_id})
    except Exception as e:
        logger.error("[delete_classroom] Announcements cascade error: %s", e)

    # ── Cascade 4: Notifications referencing this classroom ─────────
    try:
        await db.notifications.delete_many({"link": {"$regex": f"/{classroom_id}"}})
    except Exception as e:
        logger.error("[delete_classroom] Notifications cascade error: %s", e)

    # ── Finally: delete the classroom itself ────────────────────────
    await db.classrooms.delete_one({"classroom_id": classroom_id})
    logger.info("[delete_classroom] ✓ Classroom %s fully deleted", classroom_id)

    return {"message": "Classroom deleted", "classroom_id": classroom_id}
