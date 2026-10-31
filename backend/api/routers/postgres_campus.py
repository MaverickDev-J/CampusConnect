"""Campus actions with the existing REST contracts and shared transaction service."""
from datetime import date
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from api.dependencies import get_current_user
from api.routers.announcements import CreateAnnouncementBody
from api.routers.postgres_files import public_metadata
from database.postgres import principal_session

router = APIRouter(tags=["Campus"])


class EventBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    date: date
    classroom_id: str | None = None
    type: Literal['event','exam','deadline'] = 'event'


@router.post('/api/announcements', status_code=201)
async def announce(request: Request, body: CreateAnnouncementBody, principal=Depends(get_current_user),
                   idempotency_key: str | None = Header(None, max_length=200)):
    return await request.app.state.actions.create(principal, 'announcement', body, idempotency_key or uuid4().hex)


@router.get('/api/announcements/{classroom_id}')
async def announcements(classroom_id: str, request: Request, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100), principal=Depends(get_current_user)):
    await request.app.state.files.authorize(principal, classroom_id)
    async with principal_session(request.app.state.accounts.factory, principal['user_id']) as session:
        total = (await session.execute(text('SELECT count(*) FROM announcements WHERE classroom_id=:id'), {'id': classroom_id})).scalar_one()
        rows = (await session.execute(text('''SELECT a.*,u.name AS author_name,u.role AS author_role
          FROM announcements a LEFT JOIN users u ON u.user_id=a.author_id WHERE classroom_id=:id
          ORDER BY a.created_at DESC,a.announcement_id LIMIT :limit OFFSET :skip'''),
          {'id': classroom_id, 'limit': limit, 'skip': (page-1)*limit})).mappings().all()
        file_ids = [row['file_id'] for row in rows if row['file_id']]
        files = (await session.execute(text("SELECT * FROM files WHERE file_id=ANY(CAST(:ids AS text[])) AND status<>'deleted'"), {'ids': file_ids})).mappings().all() if file_ids else []
        file_map = {file['file_id']: public_metadata(dict(file)) for file in files}
        items = [{**dict(row), 'file': file_map.get(row['file_id'])} for row in rows]
        return {'announcements': items, 'count': len(items), 'total': total, 'page': page}


@router.post('/api/calendar/events', status_code=201)
async def event(request: Request, body: EventBody, principal=Depends(get_current_user),
                idempotency_key: str | None = Header(None, max_length=200)):
    return await request.app.state.actions.create(principal, 'event', body, idempotency_key or uuid4().hex)


@router.get('/api/calendar/events')
async def events(request: Request, classroom_id: str | None = None, principal=Depends(get_current_user)):
    if classroom_id:
        await request.app.state.files.authorize(principal, classroom_id)
    async with principal_session(request.app.state.accounts.factory, principal['user_id']) as session:
        rows = (await session.execute(text('''SELECT e.*,coalesce(u.name,'Campus administrator') AS creator_name,
          coalesce(c.name,'Global') AS classroom_name,coalesce(c.subject,'General') AS subject
          FROM calendar_events e LEFT JOIN users u ON u.user_id=e.created_by
          LEFT JOIN classrooms c ON c.classroom_id=e.classroom_id
          WHERE (CAST(:id AS text) IS NULL OR e.classroom_id=:id) ORDER BY e.date,e.event_id LIMIT 100'''), {'id': classroom_id})).mappings().all()
        return {'events': [dict(row) for row in rows]}


async def delete_resource(request, principal, resource_id, kind):
    table, column, owner = ('announcements','announcement_id','author_id') if kind == 'announcement' else ('calendar_events','event_id','created_by')
    async with principal_session(request.app.state.accounts.factory, principal['user_id']) as session:
        # Identifiers are a fixed internal allowlist, never interpolated user input.
        row = (await session.execute(text(f'SELECT * FROM {table} WHERE {column}=:id'), {'id': resource_id})).mappings().first()
        if not row:
            raise HTTPException(404, 'Resource not found')
        if principal['role'] != 'superadmin' and row[owner] != principal['user_id']:
            raise HTTPException(403, 'Only the author or admin can delete this resource')
        await request.app.state.actions._authorize(session, row['classroom_id'], write=True)
        deleted = await session.execute(text(f'DELETE FROM {table} WHERE {column}=:id RETURNING {column}'), {'id': resource_id})
        if not deleted.first():
            raise HTTPException(404, 'Resource not found')
        await request.app.state.actions._event(session, principal, resource_id, row['classroom_id'],
              'announcement_updated' if kind == 'announcement' else 'calendar_updated')
    return {'status': 'deleted', 'announcement_id': resource_id} if kind == 'announcement' else {'message': 'Event deleted successfully'}


@router.delete('/api/announcements/{announcement_id}')
async def remove_announcement(announcement_id: str, request: Request, principal=Depends(get_current_user)):
    # An attachment may be shared by several announcements and chat sessions.
    # Removing a post does not implicitly destroy the underlying document.
    return await delete_resource(request, principal, announcement_id, 'announcement')


@router.delete('/api/calendar/events/{event_id}')
async def remove_event(event_id: str, request: Request, principal=Depends(get_current_user)):
    return await delete_resource(request, principal, event_id, 'event')


@router.get('/api/notifications')
async def notifications(request: Request, principal=Depends(get_current_user)):
    async with principal_session(request.app.state.accounts.factory, principal['user_id']) as session:
        rows = (await session.execute(text('SELECT * FROM notifications WHERE NOT is_read ORDER BY created_at DESC,notification_id LIMIT 50'))).mappings().all()
        return {'notifications': [dict(row) for row in rows], 'count': len(rows)}


@router.patch('/api/notifications/{notification_id}/read')
async def mark_read(notification_id: str, request: Request, principal=Depends(get_current_user)):
    async with principal_session(request.app.state.accounts.factory, principal['user_id']) as session:
        row = (await session.execute(text('UPDATE notifications SET is_read=true WHERE notification_id=:id RETURNING notification_id'), {'id': notification_id})).first()
        if not row:
            raise HTTPException(404, 'Notification not found')
    return {'message': 'Marked as read'}


@router.delete('/api/notifications/clear')
async def clear(request: Request, principal=Depends(get_current_user)):
    async with principal_session(request.app.state.accounts.factory, principal['user_id']) as session:
        await session.execute(text('UPDATE notifications SET is_read=true WHERE NOT is_read'))
    return {'message': 'Notifications cleared'}
