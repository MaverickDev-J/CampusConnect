"""Registration, login, and profile routes shared by both database adapters."""

import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from core.security import hash_password, verify_password, create_access_token
from repositories.accounts import get_accounts
from sqlalchemy.exc import IntegrityError
from pymongo.errors import DuplicateKeyError
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
    Self-registration — students and teachers.
    """
    accounts = get_accounts(request)

    # 1. Duplicate email check
    if await accounts.by_email(payload.email.lower().strip()):
        raise HTTPException(status_code=409, detail="Email already registered")

    # 2. Build user document (allow student and teacher self-registration)
    role = payload.role or RoleEnum.student
    if role == RoleEnum.superadmin:
        raise HTTPException(status_code=403, detail="Cannot self-register as superadmin")

    email_lower = payload.email.lower().strip()
    user_id = _build_user_id(role)
    profile = payload.profile or {}
    
    user_doc = {
        "user_id": user_id,
        "email": email_lower,
        "name": payload.name,
        "password": await asyncio.to_thread(hash_password, payload.password),
        "role": role.value,
        "profile": profile,
    }

    try:
        await accounts.create(user_doc)
    except (IntegrityError, DuplicateKeyError):
        raise HTTPException(status_code=409, detail="Email already registered")

    return UserResponse(
        user_id=user_id,
        email=email_lower,
        name=payload.name,
        role=role,
        profile=profile,
    )


# ── POST /api/auth/login ───────────────────────────────────────────

@router.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    accounts = get_accounts(request)
    email_lower = form.username.lower().strip()

    user = await accounts.by_email(email_lower)
    if not user or not await asyncio.to_thread(verify_password, form.password, user["password"]):
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
    request: Request,
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    accounts = get_accounts(request)
    
    update_data = {}
    if payload.name:
        update_data["name"] = payload.name
        
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided")
        
    updated_user = await accounts.update(current_user["user_id"], update_data)
    # Invalidate the Redis cache so next request gets fresh data
    if accounts.uses_profile_cache:
        invalidate_user_cache(current_user["user_id"])
    
    # Fetch updated doc
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
    request: Request,
    payload: PasswordChange,
    current_user: dict = Depends(get_current_user)
):
    accounts = get_accounts(request)
    
    # Verify old password
    credential = await accounts.by_email(current_user["email"])
    if not credential or not await asyncio.to_thread(verify_password, payload.old_password, credential["password"]):
        raise HTTPException(status_code=401, detail="Invalid current password")
        
    # Hash and update
    new_hashed = await asyncio.to_thread(hash_password, payload.new_password)
    await accounts.update(current_user["user_id"], {"password": new_hashed})
    # Invalidate the Redis cache — cached user has the old password hash
    if accounts.uses_profile_cache:
        invalidate_user_cache(current_user["user_id"])

    return {"message": "Password updated successfully"}
