"""Session ownership, serialized turns, and atomic history persistence."""
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from database.postgres import principal_session


class PostgresChat:
    def __init__(self, factory):
        self.factory = factory

    async def create(self, principal, body):
        async with principal_session(self.factory, principal["user_id"]) as session:
            classroom_id = body.classroom_id
            if body.file_id:
                file = (await session.execute(text("SELECT classroom_id,status FROM files WHERE file_id=:id"), {"id": body.file_id})).first()
                if not file:
                    raise HTTPException(404, "File not found")
                if file.status != 'ready':
                    raise HTTPException(400, "File is not yet processed")
                if classroom_id and classroom_id != file.classroom_id:
                    raise HTTPException(403, "File is outside the requested classroom")
                classroom_id = file.classroom_id
            if classroom_id:
                await self.authorize_scope(session, classroom_id)
            params = {"id": "sess_" + uuid4().hex[:12], "owner": principal["user_id"], "title": body.title or "New Chat",
                      "classroom": classroom_id, "file": body.file_id}
            row = (await session.execute(text("""INSERT INTO chat_sessions(session_id,user_id,classroom_id,file_id,title)
              VALUES (:id,:owner,:classroom,:file,:title) RETURNING *"""), params)).mappings().one()
            return dict(row)

    async def authorize_scope(self, session, classroom_id):
        if not classroom_id or not (await session.execute(text("SELECT public.can_read_classroom(:id)"), {"id": classroom_id})).scalar_one():
            raise HTTPException(403, "Classroom access denied")

    async def get(self, principal, session_id):
        async with principal_session(self.factory, principal["user_id"]) as session:
            row = (await session.execute(text("SELECT * FROM chat_sessions WHERE session_id=:id"), {"id": session_id})).mappings().first()
            if not row:
                raise HTTPException(404, "Session not found")
            return dict(row)

    async def list(self, principal, classroom_id=None):
        async with principal_session(self.factory, principal["user_id"]) as session:
            return [dict(row) for row in (await session.execute(text("""SELECT * FROM chat_sessions
              WHERE (CAST(:classroom AS text) IS NULL OR classroom_id=:classroom)
              ORDER BY updated_at DESC,session_id LIMIT 200"""), {"classroom": classroom_id})).mappings()]

    async def history(self, principal, session_id):
        await self.get(principal, session_id)
        async with principal_session(self.factory, principal["user_id"]) as session:
            return [dict(row) for row in (await session.execute(text("""SELECT role,content,sources,created_at AS timestamp
              FROM chat_messages WHERE session_id=:id ORDER BY message_id LIMIT 500"""), {"id": session_id})).mappings()]

    async def modify(self, principal, session_id, title=None):
        await self.get(principal, session_id)
        async with principal_session(self.factory, principal["user_id"]) as session:
            if title is None:
                await session.execute(text("DELETE FROM chat_sessions WHERE session_id=:id"), {"id": session_id})
            else:
                await session.execute(text("UPDATE chat_sessions SET title=:title,updated_at=now() WHERE session_id=:id"), {"id": session_id, "title": title})

    async def acquire(self, principal, session_id, scope):
        saved = await self.get(principal, session_id)
        if saved["classroom_id"] and scope and saved["classroom_id"] != scope:
            raise HTTPException(403, "Start a new session to change classrooms")
        classroom = saved["classroom_id"] or scope
        async with principal_session(self.factory, principal["user_id"]) as session:
            await self.authorize_scope(session, classroom)
            token = uuid4().hex
            row = (await session.execute(text("""UPDATE chat_sessions SET run_token=:token,busy_until=now()+interval '3 minutes',classroom_id=:classroom
              WHERE session_id=:id AND (busy_until IS NULL OR busy_until<now()) RETURNING *"""),
              {"token": token, "classroom": classroom, "id": session_id})).mappings().first()
            if not row:
                raise HTTPException(409, "A response is already being generated")
            return dict(row)

    async def finish(self, principal, saved, query, answer, sources):
        async with principal_session(self.factory, principal["user_id"]) as session:
            claimed = (await session.execute(text("""UPDATE chat_sessions SET run_token=NULL,busy_until=NULL,updated_at=now()
              WHERE session_id=:session_id AND run_token=:run_token AND busy_until>now() RETURNING session_id"""), saved)).first()
            if not claimed:
                raise RuntimeError("Chat session no longer available")
            for role, content, refs in (("user", query, []), ("assistant", answer, sources)):
                await session.execute(text("""INSERT INTO chat_messages(session_id,role,content,sources)
                  VALUES (:id,:role,:content,CAST(:sources AS jsonb))"""),
                  {"id": saved["session_id"], "role": role, "content": content, "sources": json.dumps(refs)})

    async def release(self, principal, saved):
        async with principal_session(self.factory, principal["user_id"]) as session:
            await session.execute(text("UPDATE chat_sessions SET run_token=NULL,busy_until=NULL WHERE session_id=:session_id AND run_token=:run_token"), saved)
