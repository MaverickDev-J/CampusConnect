"""Auth router – register (students only), login, /users/me."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from core.security import hash_password, verify_password, create_access_token
from database.mongo import get_db
from models.schemas import (
    RoleEnum,
    UserCreate,
    UserResponse,
    TokenResponse,
    UserUpdate,
    PasswordChange,
)
from api.dependencies import get_current_user, invalidate_user_cache

router = APIRouter()

# ── Helpers ─────────────────────────────────────────────────────────

_ROLE_PREFIX = {
    RoleEnum.student: "stu",
    RoleEnum.teacher: "tea",
    RoleEnum.superadmin: "adm",
}


def _build_user_id(role: RoleEnum) -> str:
    return f"{_ROLE_PREFIX[role]}_{uuid4().hex[:12]}"


# ── POST /api/auth/register ────────────────────────────────────────

@router.post(
    "/api/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
)
async def register(request: Request, payload: UserCreate):
    """
    Self-registration — students only.

    Teachers are provisioned by the Superadmin via /api/superadmin/provision-teacher.
    """
    db = get_db()

    # 1. Duplicate email check
    if await db.users.find_one({"email": payload.email}):
        raise HTTPException(status_code=409, detail="Email already registered")

    # 2. Build user document (student role only for self-registration)
    email_lower = payload.email.lower().strip()
    user_id = _build_user_id(RoleEnum.student)
    profile = payload.profile or {}
    
    user_doc = {
        "user_id": user_id,
        "email": email_lower,
        "name": payload.name,
        "password": hash_password(payload.password),
        "role": RoleEnum.student.value,
        "profile": profile,
    }

    await db.users.insert_one(user_doc)

    return UserResponse(
        user_id=user_id,
        email=payload.email,
        name=payload.name,
        role=RoleEnum.student,
        profile=profile,
    )


# ── POST /api/auth/login ───────────────────────────────────────────

@router.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    email_lower = form.username.lower().strip()

    user = await db.users.find_one({"email": email_lower})
    if not user or not verify_password(form.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # JWT payload — minimal claims
    token_data = {
        "user_id": user["user_id"],
        "role": user["role"],
    }

    access_token = create_access_token(data=token_data)
    return TokenResponse(access_token=access_token)


# ── GET /api/users/me ──────────────────────────────────────────────

@router.get("/api/users/me", response_model=UserResponse, tags=["Users"])
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        user_id=current_user["user_id"],
        email=current_user["email"],
        name=current_user["name"],
        role=current_user["role"],
        profile=current_user.get("profile", {}),
    )


# ── PATCH /api/users/me ────────────────────────────────────────────

@router.patch("/api/users/me", response_model=UserResponse, tags=["Users"])
async def update_me(
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    
    update_data = {}
    if payload.name:
        update_data["name"] = payload.name
        
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")
        
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": update_data}
    )
    # Invalidate the Redis cache so next request gets fresh data
    invalidate_user_cache(current_user["user_id"])
    
    # Fetch updated doc
    updated_user = await db.users.find_one({"user_id": current_user["user_id"]})
    return UserResponse(
        user_id=updated_user["user_id"],
        email=updated_user["email"],
        name=updated_user["name"],
        role=updated_user["role"],
        profile=updated_user.get("profile", {}),
    )


# ── POST /api/users/me/password ────────────────────────────────────

@router.post("/api/users/me/password", tags=["Users"])
async def change_password(
    payload: PasswordChange,
    current_user: dict = Depends(get_current_user)
):
    db = get_db()
    
    # Verify old password
    if not verify_password(payload.old_password, current_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid current password")
        
    # Hash and update
    new_hashed = hash_password(payload.new_password)
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"password": new_hashed}}
    )
    # Invalidate the Redis cache — cached user has the old password hash
    invalidate_user_cache(current_user["user_id"])

    return {"message": "Password updated successfully"}
