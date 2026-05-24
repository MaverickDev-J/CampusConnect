"""Superadmin router – provision teachers, list users."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import require_role
from core.security import hash_password
from database.mongo import get_db
from models.schemas import ProvisionTeacherBody, RoleEnum, UserResponse

router = APIRouter(prefix="/api/superadmin", tags=["Superadmin"])


# ── POST /api/superadmin/provision-teacher ──────────────────────────

@router.post(
    "/provision-teacher",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_teacher(
    body: ProvisionTeacherBody,
    current_user: dict = Depends(require_role("superadmin")),
):
    """Create a new teacher account. Superadmin only."""
    db = get_db()
    email_lower = body.email.lower().strip()

    if await db.users.find_one({"email": email_lower}):
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = f"tea_{uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": email_lower,
        "name": body.name,
        "password": hash_password(body.password),
        "role": RoleEnum.teacher.value,
        "profile": {},
    }

    await db.users.insert_one(user_doc)
    return UserResponse(
        user_id=user_id,
        email=body.email,
        name=body.name,
        role=RoleEnum.teacher,
        profile={},
    )


# ── GET /api/superadmin/users ──────────────────────────────────────

@router.get("/users", status_code=status.HTTP_200_OK)
async def list_users(
    role: str | None = Query(None, description="Filter by role: student|teacher|superadmin"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_role("superadmin")),
):
    """List all users with optional role filter. Superadmin only. Paginated."""
    db = get_db()

    query: dict = {}
    if role:
        query["role"] = role

    skip = (page - 1) * limit
    total = await db.users.count_documents(query)
    cursor = db.users.find(query, {"password": 0, "_id": 0}).skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)

    return {"users": users, "count": len(users), "total": total, "page": page}


# ── DELETE /api/superadmin/users/{user_id} ──────────────────────────

@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: str,
    current_user: dict = Depends(require_role("superadmin")),
):
    """Delete a user by user_id. Superadmin only. Cannot delete self."""
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own superadmin account")

    db = get_db()
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.users.delete_one({"user_id": user_id})
    return {"message": "User deleted", "user_id": user_id}
