"""Announcements router — teachers create, everyone reads."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_current_user
from database.chroma import get_chroma_collection
from database.mongo import get_db
from core.websocket import manager

router = APIRouter(prefix="/api/announcements", tags=["Announcements"])
logger = logging.getLogger(__name__)


class CreateAnnouncementBody(BaseModel):
    classroom_id: str
    content: str | None = Field(None, max_length=5000)
    file_id: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_announcement(
    body: CreateAnnouncementBody,
    current_user: dict = Depends(get_current_user),
):
    """Create an announcement. Teachers and superadmins only."""
    if current_user.get("role") not in ("teacher", "superadmin"):
        raise HTTPException(status_code=403, detail="Only teachers can post announcements")

    db = get_db()

    # Verify classroom exists
    classroom = await db.classrooms.find_one({"classroom_id": body.classroom_id})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # ── Verify the teacher is a MEMBER of this classroom ──────────
    # (Fixes: any teacher could post to any classroom if they knew its ID)
    if current_user["role"] != "superadmin":
        member_ids = [m["user_id"] for m in classroom.get("members", [])]
        if current_user["user_id"] not in member_ids:
            raise HTTPException(
                status_code=403,
                detail="You must be a member of this classroom to post announcements",
            )

    # Content validation
    final_content = body.content
    if not final_content or not final_content.strip():
        if body.file_id:
            final_content = "File Uploaded"
        else:
            raise HTTPException(
                status_code=400,
                detail="Announcement must have content or a file attached.",
            )

    ann_id = f"ann_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    announcement_doc = {
        "announcement_id": ann_id,
        "classroom_id": body.classroom_id,
        "author_id": current_user["user_id"],
        "author_name": current_user["name"],
        "author_role": current_user["role"],
        "content": final_content,
        "file_id": body.file_id,
        "created_at": now,
    }

    await db.announcements.insert_one(announcement_doc)

    # ── Batch-create notifications for all classroom members ───────
    members = classroom.get("members", [])
    notifications = [
        {
            "notification_id": f"notif_{uuid4().hex[:12]}",
            "user_id": m["user_id"],
            "type": "announcement",
            "title": f"New Announcement in {classroom['name']}",
            "message": final_content[:100] + ("..." if len(final_content) > 100 else ""),
            "link": f"/classroom/{body.classroom_id}",
            "is_read": False,
            "created_at": now,
        }
        for m in members
        if m["user_id"] != current_user["user_id"]  # Don't notify self
    ]
    if notifications:
        await db.notifications.insert_many(notifications)

    # ── WebSocket broadcast ────────────────────────────────────────
    await manager.publish_update(body.classroom_id, {"type": "announcement_updated"})

    return {
        "announcement_id": ann_id,
        "content": final_content,
        "author_name": current_user["name"],
        "author_role": current_user["role"],
        "file_id": body.file_id,
        "created_at": now.isoformat(),
    }


@router.get("/{classroom_id}")
async def list_announcements(
    classroom_id: str,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Return announcements for a classroom, newest first. Paginated."""
    db = get_db()
    skip = (max(page, 1) - 1) * min(limit, 100)

    total = await db.announcements.count_documents({"classroom_id": classroom_id})
    cursor = (
        db.announcements.find({"classroom_id": classroom_id}, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(min(limit, 100))
    )
    items = await cursor.to_list(length=min(limit, 100))

    # ── Batch-fetch all file metadata in ONE query (fixes N+1) ─────
    file_ids = [item["file_id"] for item in items if item.get("file_id")]
    file_map: dict = {}
    if file_ids:
        file_cursor = db.file_metadata.find(
            {"file_id": {"$in": file_ids}},
            {"_id": 0, "storage_path": 0, "sha256_hash": 0},
        )
        file_docs = await file_cursor.to_list(length=len(file_ids))
        file_map = {f["file_id"]: f for f in file_docs}

    for item in items:
        if isinstance(item.get("created_at"), datetime):
            item["created_at"] = item["created_at"].isoformat()
        if item.get("file_id"):
            item["file"] = file_map.get(item["file_id"])

    return {"announcements": items, "count": len(items), "total": total, "page": page}


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete an announcement, its file, and its ChromaDB vectors."""
    if current_user.get("role") not in ("teacher", "superadmin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    db = get_db()
    ann = await db.announcements.find_one({"announcement_id": announcement_id})
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if current_user["role"] != "superadmin" and ann.get("author_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Cannot delete another teacher's announcement")

    # ── Cascade: delete associated file, vectors, metadata ─────────
    if ann.get("file_id"):
        file_id = ann["file_id"]
        file_meta = await db.file_metadata.find_one({"file_id": file_id})

        if file_meta:
            # 1. Delete physical file
            storage_path = file_meta.get("storage_path")
            if storage_path and os.path.exists(storage_path):
                try:
                    os.remove(storage_path)
                except Exception as e:
                    logger.warning("[delete_announcement] Could not delete file %s: %s", storage_path, e)

            # 2. Delete ChromaDB vectors
            try:
                collection = get_chroma_collection()
                collection.delete(where={"file_id": file_id})
            except Exception as e:
                logger.warning("[delete_announcement] Could not delete vectors for %s: %s", file_id, e)

            # 3. Delete file metadata
            await db.file_metadata.delete_one({"file_id": file_id})

    await db.announcements.delete_one({"announcement_id": announcement_id})
    await manager.publish_update(ann["classroom_id"], {"type": "announcement_updated"})

    return {"status": "deleted", "announcement_id": announcement_id}
