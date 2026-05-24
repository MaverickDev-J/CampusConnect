"""Admin router – grant/revoke upload permissions, list users."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_current_user
from database.mongo import get_db
from models.schemas import AdminTargetUser

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ── Helpers ─────────────────────────────────────────────────────────

def _require_admin(current_user: dict) -> None:
    """Raise 403 if the requesting user is not an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can perform this action",
        )


# ── PATCH /api/admin/grant-upload ───────────────────────────────────

@router.patch("/grant-upload", status_code=status.HTTP_200_OK)
async def grant_upload(
    body: AdminTargetUser,
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    db = get_db()

    target = await db.users.find_one({"user_id": body.target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.get("role") != "student":
        raise HTTPException(status_code=400, detail="Can only grant upload to students")

    await db.users.update_one(
        {"user_id": body.target_user_id},
        {"$set": {"profile.can_upload": True}},
    )

    return {"message": "Upload permission granted", "user_id": body.target_user_id}


# ── PATCH /api/admin/revoke-upload ──────────────────────────────────

@router.patch("/revoke-upload", status_code=status.HTTP_200_OK)
async def revoke_upload(
    body: AdminTargetUser,
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    db = get_db()

    target = await db.users.find_one({"user_id": body.target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.get("role") != "student":
        raise HTTPException(status_code=400, detail="Can only revoke upload from students")

    await db.users.update_one(
        {"user_id": body.target_user_id},
        {"$set": {"profile.can_upload": False}},
    )

    return {"message": "Upload permission revoked", "user_id": body.target_user_id}


# ── GET /api/admin/users ────────────────────────────────────────────

@router.get("/users", status_code=status.HTTP_200_OK)
async def list_users(
    role: Optional[str] = Query(None, description="Filter by role (admin, faculty, student)"),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    db = get_db()

    query: dict = {}
    if role:
        query["role"] = role

    cursor = db.users.find(query, {"password": 0, "_id": 0})
    users = await cursor.to_list(length=1000)

    return {"users": users, "count": len(users)}
