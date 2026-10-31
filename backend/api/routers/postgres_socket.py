"""Authenticated Redis-to-WebSocket gateway with current database authorization."""
import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import jwt
from sqlalchemy import text
from core.security import decode_access_token
from database.postgres import principal_session

router = APIRouter()


async def authorized(app, token, room):
    try:
        user_id = decode_access_token(token).get('user_id')
        user = await app.state.accounts.by_id(user_id) if user_id else None
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return False
    if not user:
        return False
    if room == 'global_events':
        return True
    async with principal_session(app.state.accounts.factory, user_id) as session:
        row = (await session.execute(text('SELECT classroom_id FROM classrooms WHERE classroom_id=:id'), {'id':room})).first()
        return row is not None


@router.websocket('/ws/classroom/{classroom_id}')
async def classroom_socket(websocket: WebSocket, classroom_id: str, token: str | None = None):
    app = websocket.app
    origin = websocket.headers.get('origin')
    if origin and origin not in app.state.ws_origins:
        await websocket.close(code=4003, reason='Origin not allowed')
        return
    if not token:
        await websocket.close(code=4001, reason='Authentication required')
        return
    if not await authorized(app, token, classroom_id):
        await websocket.close(code=4003, reason='Classroom access denied')
        return
    tasks = []
    lock = asyncio.Lock()
    async def send(payload):
        async with lock:
            await websocket.send_text(payload if isinstance(payload,str) else json.dumps(payload))
    try:
        async with app.state.ws_redis.pubsub() as pubsub:
            await pubsub.subscribe('classroom_updates')
            await websocket.accept()
            await send({'type':'connection_established','classroom_id':classroom_id,'status':'ready'})

            async def receive():
                while True:
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                    if not await authorized(app, token, classroom_id):
                        await websocket.close(code=4003, reason='Access revoked')
                        return
                    if message == 'ping':
                        await send('pong')

            async def updates():
                checked = time.monotonic()
                while True:
                    if time.monotonic()-checked >= 15:
                        if not await authorized(app, token, classroom_id):
                            await websocket.close(code=4003, reason='Access revoked')
                            return
                        checked = time.monotonic()
                    event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                    if not event:
                        await asyncio.sleep(0.05)
                        continue
                    try:
                        data = json.loads(event['data'])
                        if not isinstance(data,dict):
                            continue
                        room, payload = data.get('classroom_id'), data.get('payload')
                        if not isinstance(payload,dict):
                            continue
                    except (ValueError,KeyError,TypeError):
                        continue
                    relevant = room == classroom_id
                    if classroom_id == 'global_events' and payload.get('type') == 'calendar_updated':
                        relevant = room == 'global_events' or await authorized(app, token, room)
                    if not relevant:
                        continue
                    if not await authorized(app, token, classroom_id):
                        await websocket.close(code=4003, reason='Access revoked')
                        return
                    await send(payload)

            tasks = [asyncio.create_task(receive()), asyncio.create_task(updates())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        await websocket.close(code=4000, reason='Heartbeat expired')
    except Exception:
        # Redis outages close the connection so the client's existing backoff
        # reconnects. Never log a WebSocket URL containing its bearer token.
        try:
            await websocket.close(code=1013, reason='Updates temporarily unavailable')
        except Exception:
            pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
