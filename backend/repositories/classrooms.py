"""Transactional classroom operations with current-principal database policies."""
import secrets
import string
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from database.postgres import principal_session


class PostgresClassrooms:
    def __init__(self, factory):
        self.factory = factory

    async def create(self, principal, body):
        if principal["role"] not in {"teacher", "superadmin"}:
            raise HTTPException(403, "Only teachers can create classrooms")
        for _ in range(10):
            try:
                async with principal_session(self.factory, principal["user_id"]) as session:
                    params = {"id": f"cls_{uuid4().hex[:12]}", "name": body.name,
                              "description": body.description, "subject": body.subject,
                              "code": ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6)),
                              "owner": principal["user_id"]}
                    await session.execute(text("""INSERT INTO classrooms
                        (classroom_id,name,description,subject,join_code,created_by)
                        VALUES (:id,:name,:description,:subject,:code,:owner)"""), params)
                    row = (await session.execute(text("SELECT * FROM classrooms WHERE classroom_id=:id"), params)).mappings().one()
                    await session.execute(text("INSERT INTO classroom_members(classroom_id,user_id) VALUES (:id,:owner)"), params)
                    return {**dict(row), "created_at": row["created_at"].isoformat(),
                            "member_count": 1, "created_by_name": principal["name"]}
            except IntegrityError as exc:
                if getattr(exc.orig, "sqlstate", None) != "23505":
                    raise
        raise HTTPException(503, "Could not allocate a classroom code")

    async def list(self, principal, page, limit):
        page, limit = max(page, 1), max(1, min(limit, 100))
        async with principal_session(self.factory, principal["user_id"]) as session:
            total = (await session.execute(text("SELECT count(*) FROM classrooms"))).scalar_one()
            rows = (await session.execute(text("""SELECT c.*,u.name AS created_by_name,
                (SELECT count(*) FROM classroom_members m WHERE m.classroom_id=c.classroom_id) AS member_count
                FROM classrooms c JOIN users u ON u.user_id=c.created_by
                ORDER BY c.updated_at DESC,c.classroom_id LIMIT :limit OFFSET :skip"""),
                {"limit": limit, "skip": (page - 1) * limit})).mappings().all()
            return {"classrooms": [dict(row) for row in rows], "count": len(rows), "total": total, "page": page}

    async def detail(self, principal, classroom_id):
        async with principal_session(self.factory, principal["user_id"]) as session:
            row = (await session.execute(text("""SELECT c.*,u.name AS created_by_name
                FROM classrooms c JOIN users u ON u.user_id=c.created_by
                WHERE classroom_id=:id"""), {"id": classroom_id})).mappings().first()
            if not row:
                raise HTTPException(404, "Classroom not found")
            members = (await session.execute(text("""SELECT m.user_id,u.role,u.name,u.email,m.joined_at
                FROM classroom_members m JOIN users u ON u.user_id=m.user_id
                WHERE m.classroom_id=:id ORDER BY m.joined_at,m.user_id"""), {"id": classroom_id})).mappings().all()
            return {**dict(row), "members": [dict(m) for m in members], "member_count": len(members)}

    async def join(self, principal, code):
        async with principal_session(self.factory, principal["user_id"]) as session:
            row = (await session.execute(text("SELECT * FROM public.join_classroom(:code)"), {"code": code})).mappings().first()
            if not row:
                raise HTTPException(404, "Invalid join code")
            return {"message": "Already a member of this classroom" if row["already_member"] else "Successfully joined classroom",
                    "classroom_id": row["classroom_id"], "name": row["name"], "join_code": row["join_code"]}

    async def delete(self, principal, classroom_id):
        async with principal_session(self.factory, principal["user_id"]) as session:
            row = (await session.execute(text("SELECT created_by FROM classrooms WHERE classroom_id=:id FOR UPDATE"), {"id": classroom_id})).first()
            if not row:
                raise HTTPException(404, "Classroom not found")
            if principal["role"] != "superadmin" and row.created_by != principal["user_id"]:
                raise HTTPException(403, "Only the classroom creator or admin can delete it")
            # File cleanup needs a durable outbox before this route can delete uploads.
            files = (await session.execute(text("SELECT count(*) FROM files WHERE classroom_id=:id"), {"id": classroom_id})).scalar_one()
            if files:
                raise HTTPException(409, "Classroom file cleanup is not migrated yet")
            await session.execute(text("DELETE FROM classrooms WHERE classroom_id=:id"), {"id": classroom_id})
        return {"message": "Classroom deleted", "classroom_id": classroom_id}
