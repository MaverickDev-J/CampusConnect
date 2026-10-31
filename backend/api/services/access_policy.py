"""Shared resource policy for REST handlers and future MCP tools."""

from fastapi import HTTPException


async def authorize_classroom(db, classroom_id: str, principal: dict, *, write=False):
    """Resolve current membership from storage rather than cached profile claims."""
    if write and principal.get("role") not in {"teacher", "superadmin"}:
        raise HTTPException(403, "Only teachers and admins can modify classrooms")
    classroom = await db.classrooms.find_one({"classroom_id": classroom_id})
    if not classroom:
        raise HTTPException(404, "Classroom not found")
    user_id = principal.get("user_id")
    members = {member["user_id"] for member in classroom.get("members", [])}
    if principal.get("role") != "superadmin" and (
        not user_id or (user_id != classroom.get("created_by") and user_id not in members)
    ):
        raise HTTPException(403, "You are not a member of this classroom")
    return classroom


async def authorize_file(db, file_id: str, principal: dict, *, classroom_id=None):
    """A file ID cannot override the authenticated classroom boundary."""
    document = await db.file_metadata.find_one({"file_id": file_id})
    if not document:
        raise HTTPException(404, "File not found")
    if classroom_id is not None and document.get("classroom_id") != classroom_id:
        raise HTTPException(403, "File does not belong to this classroom")
    await authorize_classroom(db, document["classroom_id"], principal)
    return document
