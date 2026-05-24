from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from api.dependencies import get_current_user, require_classroom_member
from database.mongo import get_db
from models.schemas import CalendarEventCreate
from core.websocket import manager

router = APIRouter(prefix="/api/calendar", tags=["Calendar"])

@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CalendarEventCreate,
    current_user: dict = Depends(get_current_user)
):
    """Teachers and Admins can create calendar events."""
    if current_user["role"] not in ("teacher", "superadmin"):
        raise HTTPException(
            status_code=403, 
            detail="Only teachers and admins can create events"
        )
    
    db = get_db()
    event_id = f"ev_{uuid4().hex[:12]}"
    
    event_doc = {
        "event_id": event_id,
        "title": body.title,
        "description": body.description,
        "date": body.date,
        "classroom_id": body.classroom_id,
        "type": body.type,
        "created_by": current_user["user_id"],
        "created_at": datetime.utcnow()
    }
    
    await db.calendar_events.insert_one(event_doc)

    # ── Notification Logic ──
    notifications = []
    if event_doc.get("classroom_id"):
        # Scoped to classroom: Notify members
        classroom = await db.classrooms.find_one({"classroom_id": event_doc["classroom_id"]})
        if classroom:
            members = classroom.get("members", [])
            for member in members:
                if member["user_id"] != current_user["user_id"]:
                    notifications.append({
                        "notification_id": f"notif_{uuid4().hex[:12]}",
                        "user_id": member["user_id"],
                        "type": "event",
                        "title": f"New Event: {event_doc['title']}",
                        "message": f"In {classroom['name']} on {event_doc['date']}",
                        "link": "/calendar",
                        "is_read": False,
                        "created_at": datetime.now(timezone.utc)
                    })
    else:
        # Global event: Notify all students
        cursor = db.users.find({"role": "student"}, {"user_id": 1})
        students = await cursor.to_list(None)
        for stu in students:
            if stu["user_id"] != current_user["user_id"]:
                notifications.append({
                    "notification_id": f"notif_{uuid4().hex[:12]}",
                    "user_id": stu["user_id"],
                    "type": "event",
                    "title": f"Global Event: {event_doc['title']}",
                    "message": f"Scheduled for {event_doc['date']}",
                    "link": "/calendar",
                    "is_read": False,
                    "created_at": datetime.now(timezone.utc)
                })
    
    if notifications:
        # Use a large batch size or insert_many
        # If there are thousands of students, this might be slow, but for campus context it's usually fine.
        await db.notifications.insert_many(notifications)

    # ── WebSocket Broadcast (via Redis PubSub) ──
    # 1. Scoped broadcast
    cid = event_doc.get("classroom_id")
    if cid:
        await manager.publish_update(cid, {"type": "calendar_updated"})
    
    # 2. Always broadcast to global_events for anyone on the Calendar page
    await manager.publish_update("global_events", {"type": "calendar_updated"})

    return {"message": "Event created", "event_id": event_id}

@router.get("/events")
async def list_events(
    classroom_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List calendar events. Students can see events for their classrooms."""
    db = get_db()
    query = {}
    
    if classroom_id:
        # Verify membership if classroom scoped
        if current_user["role"] != "superadmin":
            await require_classroom_member(classroom_id, current_user["user_id"])
        query["classroom_id"] = classroom_id
    else:
        # If global list, only show events for classrooms user is member of
        if current_user["role"] != "superadmin":
            # Get user's classrooms
            user_classes = await db.classrooms.find(
                {"members.user_id": current_user["user_id"]},
                {"classroom_id": 1}
            ).to_list(100)
            class_ids = [c["classroom_id"] for c in user_classes]
            query["$or"] = [
                {"classroom_id": {"$in": class_ids}},
                {"classroom_id": {"$in": [None, ""]}} # Global events (None or empty string)
            ]

    cursor = db.calendar_events.find(query, {"_id": 0}).sort("date", 1)
    events = await cursor.to_list(100)
    
    # Enrich events
    enriched_events = []
    for event in events:
        # Get creator name
        creator = await db.users.find_one({"user_id": event.get("created_by")}, {"name": 1})
        event["creator_name"] = creator["name"] if creator else "Unknown"
        
        # Get classroom/subject info
        if event.get("classroom_id"):
            cls = await db.classrooms.find_one({"classroom_id": event["classroom_id"]}, {"name": 1, "subject": 1})
            if cls:
                event["classroom_name"] = cls["name"]
                event["subject"] = cls.get("subject", "N/A")
        else:
            event["classroom_name"] = "Global"
            event["subject"] = "General"
            
        enriched_events.append(event)
        
    return {"events": enriched_events}

@router.delete("/events/{event_id}", status_code=status.HTTP_200_OK)
async def delete_event(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete an event. Only the creator or superadmin can delete."""
    db = get_db()
    event = await db.calendar_events.find_one({"event_id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    if current_user["role"] != "superadmin" and event.get("created_by") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the creator or admin can delete this event")
        
    await db.calendar_events.delete_one({"event_id": event_id})
    
    # ── WebSocket Broadcast (via Redis PubSub) ──
    cid = event.get("classroom_id")
    if cid:
        await manager.publish_update(cid, {"type": "calendar_updated"})
    
    await manager.publish_update("global_events", {"type": "calendar_updated"})
    return {"message": "Event deleted successfully"}
