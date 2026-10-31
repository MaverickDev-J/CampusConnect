"""Shared transactional actions for REST and the forthcoming approved MCP tools."""
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from database.postgres import principal_session


class CampusActions:
    def __init__(self, factory):
        self.factory = factory

    async def _authorize(self, session, classroom_id, *, write=False):
        if classroom_id is None:
            allowed = (await session.execute(text("SELECT public.actor_role()='superadmin'"))).scalar_one()
        else:
            exists = (await session.execute(text("SELECT classroom_id FROM classrooms WHERE classroom_id=:id"), {"id": classroom_id})).first()
            if not exists:
                raise HTTPException(404, "Classroom not found")
            allowed = (await session.execute(text("SELECT public.can_write_classroom(:id)" if write else "SELECT public.can_read_classroom(:id)"), {"id": classroom_id})).scalar_one()
        if not allowed:
            raise HTTPException(403, "Classroom access denied")

    async def _operation(self, session, principal, key, payload):
        if not key or len(key) > 200:
            raise HTTPException(400, "Invalid operation key")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        params = {"actor": principal["user_id"], "key": key, "hash": digest}
        await session.execute(text("INSERT INTO campus_operations(actor_id,operation_key,payload_hash) VALUES (:actor,:key,:hash) ON CONFLICT DO NOTHING"), params)
        row = (await session.execute(text("SELECT payload_hash,result FROM campus_operations WHERE actor_id=:actor AND operation_key=:key FOR UPDATE"), params)).mappings().one()
        if row["payload_hash"] != digest:
            raise HTTPException(409, "Operation key was already used for different content")
        return row["result"]

    async def _result(self, session, principal, key, result):
        await session.execute(text("UPDATE campus_operations SET result=CAST(:result AS jsonb) WHERE actor_id=:actor AND operation_key=:key"),
          {"result": json.dumps(result), "actor": principal["user_id"], "key": key})

    async def _notify(self, session, principal, resource, classroom, kind, title, message, link):
        params = {"resource": resource, "classroom": classroom, "kind": kind, "title": title,
                  "message": message[:500], "link": link, "actor": principal["user_id"]}
        recipients = "SELECT user_id FROM classroom_members WHERE classroom_id=:classroom" if classroom else "SELECT user_id FROM users WHERE role='student'"
        await session.execute(text("""INSERT INTO notifications(notification_id,user_id,classroom_id,type,title,message,link,resource_id)
          SELECT 'notif_'||md5(:resource||':'||u.user_id),u.user_id,:classroom,:kind,:title,:message,:link,:resource
          FROM (""" + recipients + ") u WHERE u.user_id<>:actor ON CONFLICT DO NOTHING"), params)
        await self._event(session, principal, resource, classroom, "announcement_updated" if kind == "announcement" else "calendar_updated")

    async def _event(self, session, principal, resource, classroom, kind):
        await session.execute(text("""INSERT INTO campus_outbox(event_id,actor_id,classroom_id,event_type,resource_id)
          VALUES (:id,:actor,:classroom,:kind,:resource)"""), {"id": uuid4().hex, "actor": principal["user_id"],
          "classroom": classroom, "kind": kind, "resource": resource})

    async def _announcement(self, session, principal, body):
        await self._authorize(session, body.classroom_id, write=True)
        if body.file_id:
            valid = (await session.execute(text("SELECT file_id FROM files WHERE file_id=:file AND classroom_id=:classroom AND status<>'deleted'"),
              {"file": body.file_id, "classroom": body.classroom_id})).first()
            if not valid:
                raise HTTPException(403, "File is outside the classroom or unavailable")
        content = (body.content or "").strip()
        if not content and not body.file_id:
            raise HTTPException(400, "Announcement must have content or a file")
        content = content or "File Uploaded"
        resource = "ann_" + uuid4().hex[:12]
        row = (await session.execute(text("""INSERT INTO announcements(announcement_id,classroom_id,author_id,content,file_id)
          VALUES (:id,:classroom,:actor,:content,:file) RETURNING created_at"""), {"id": resource, "classroom": body.classroom_id,
          "actor": principal["user_id"], "content": content, "file": body.file_id})).one()
        await self._notify(session, principal, resource, body.classroom_id, "announcement", "New Announcement", content, f"/classroom/{body.classroom_id}")
        return {"announcement_id": resource, "content": content, "author_name": principal["name"], "author_role": principal["role"],
                "file_id": body.file_id, "created_at": row.created_at.isoformat()}

    async def _calendar(self, session, principal, body):
        await self._authorize(session, body.classroom_id, write=True)
        resource = "ev_" + uuid4().hex[:12]
        await session.execute(text("""INSERT INTO calendar_events(event_id,classroom_id,created_by,title,description,date,type)
          VALUES (:id,:classroom,:actor,:title,:description,:date,:type)"""), {"id": resource, "classroom": body.classroom_id,
          "actor": principal["user_id"], "title": body.title, "description": body.description, "date": body.date, "type": body.type})
        await self._notify(session, principal, resource, body.classroom_id, "event", f"New Event: {body.title}",
                           f"Scheduled for {body.date}", "/calendar")
        return {"message": "Event created", "event_id": resource}

    async def create(self, principal, kind, body, key):
        async with principal_session(self.factory, principal["user_id"]) as session:
            await self._authorize(session, body.classroom_id, write=True)
            result = await self._operation(session, principal, key, {"kind": kind, **body.model_dump(mode="json")})
            if result is not None:
                return result
            result = await (self._announcement(session, principal, body) if kind == "announcement" else self._calendar(session, principal, body))
            await self._result(session, principal, key, result)
            return result

    async def revision_session(self, principal, announcement, event, key):
        """Execute only after the workflow has verified human approval of this payload."""
        if not event.classroom_id or announcement.classroom_id != event.classroom_id:
            raise HTTPException(400, "Both actions require the same classroom")
        async with principal_session(self.factory, principal["user_id"]) as session:
            await self._authorize(session, event.classroom_id, write=True)
            result = await self._operation(session, principal, key, {"kind": "revision", "announcement": announcement.model_dump(mode="json"), "event": event.model_dump(mode="json")})
            if result is not None:
                return result
            result = {"announcement": await self._announcement(session, principal, announcement),
                      "event": await self._calendar(session, principal, event)}
            await self._result(session, principal, key, result)
            return result
