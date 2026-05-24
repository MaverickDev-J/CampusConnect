"""Pydantic v2 schemas and Enums for CampusMind (Classroom Architecture)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field


# ── Enums ────────────────────────────────────────────────────────────

class RoleEnum(str, Enum):
    superadmin = "superadmin"
    teacher = "teacher"
    student = "student"


# ── Request schemas ──────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Self-registration — students only."""
    email: EmailStr                                      # Proper email validation
    name: str = Field(..., min_length=1, max_length=100, strip_whitespace=True)
    password: str = Field(..., min_length=8, max_length=128)
    profile: Optional[Dict[str, Any]] = None

    model_config = {"json_schema_extra": {
        "examples": [
            {
                "email": "stu@college.com",
                "name": "John Doe",
                "password": "secret123",
                "profile": {"roll_no": "221001"},
            }
        ]
    }}


class ProvisionTeacherBody(BaseModel):
    """Superadmin creates a teacher account."""
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100, strip_whitespace=True)
    password: str = Field(..., min_length=8, max_length=128)

    model_config = {"json_schema_extra": {
        "examples": [
            {
                "email": "prof@college.com",
                "name": "Prof. Jane Smith",
                "password": "secret12345",
            }
        ]
    }}


class ClassroomCreate(BaseModel):
    """Teacher creates a new classroom."""
    name: str = Field(..., min_length=1, max_length=200, strip_whitespace=True)
    description: Optional[str] = Field(None, max_length=1000)
    subject: Optional[str] = Field(None, max_length=200, strip_whitespace=True)


class JoinClassroomBody(BaseModel):
    """Student joins a classroom via join code."""
    join_code: str = Field(..., min_length=6, max_length=6)


class CalendarEventCreate(BaseModel):
    """Teacher or admin creates a calendar event."""
    title: str = Field(..., min_length=1, max_length=200, strip_whitespace=True)
    description: Optional[str] = Field(None, max_length=1000)
    date: str = Field(..., description="ISO date string YYYY-MM-DD")
    classroom_id: Optional[str] = None
    type: str = Field("event", description="event|exam|deadline")


class UserUpdate(BaseModel):
    """Update profile info."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, strip_whitespace=True)


class PasswordChange(BaseModel):
    """Change user password."""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


# ── Response schemas ─────────────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: RoleEnum
    profile: Dict[str, Any] = {}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ClassroomResponse(BaseModel):
    classroom_id: str
    name: str
    description: Optional[str] = None
    subject: Optional[str] = None
    join_code: str
    member_count: int
    created_by: str
    created_by_name: Optional[str] = None
    created_at: str
