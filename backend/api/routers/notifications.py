from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from api.dependencies import get_current_user
from database.mongo import get_db

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    """Fetch unread notifications for the current user."""
    db = get_db()
    cursor = db.notifications.find(
        {"user_id": current_user["user_id"], "is_read": False},
        {"_id": 0}
    ).sort("created_at", -1)
    
    notifications = await cursor.to_list(length=50)
    return {"notifications": notifications, "count": len(notifications)}

@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark a specific notification as read."""
    db = get_db()
    result = await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user["user_id"]},
        {"$set": {"is_read": True}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    return {"message": "Marked as read"}

@router.delete("/clear")
async def clear_notifications(current_user: dict = Depends(get_current_user)):
    """Mark all notifications for the user as read (effectively clearing the unread list)."""
    db = get_db()
    await db.notifications.update_many(
        {"user_id": current_user["user_id"]},
        {"$set": {"is_read": True}}
    )
    return {"message": "Notifications cleared"}
