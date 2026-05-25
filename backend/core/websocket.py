"""
websocket.py — Classroom-aware WebSocket Connection Manager.
===========================================================
Handles real-time message broadcasting (Announcements, Events, Ingestion Status).
"""

import json
import logging
import asyncio
from typing import Dict, List
from fastapi import WebSocket
from database.redis import get_redis

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps classroom_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, classroom_id: str):
        await websocket.accept()
        # Send initial connection success message (Handshake Ack)
        await websocket.send_json({
            "type": "connection_established",
            "classroom_id": classroom_id,
            "status": "ready"
        })
        if classroom_id not in self.active_connections:
            self.active_connections[classroom_id] = []
        self.active_connections[classroom_id].append(websocket)

    def disconnect(self, websocket: WebSocket, classroom_id: str):
        if classroom_id in self.active_connections:
            if websocket in self.active_connections[classroom_id]:
                self.active_connections[classroom_id].remove(websocket)
            if not self.active_connections[classroom_id]:
                del self.active_connections[classroom_id]

    async def broadcast_to_classroom(self, classroom_id: str, message: dict):
        """Send a JSON message to all users in a specific classroom."""
        if classroom_id in self.active_connections:
            msg_json = json.dumps(message)
            for connection in self.active_connections[classroom_id]:
                try:
                    await connection.send_text(msg_json)
                except Exception:
                    # Connection might be stale
                    pass

    async def listen_to_redis(self):
        """
        Background task to listen for broadcast messages from Redis PubSub.
        Auto-reconnects on failure with exponential backoff (max 30s).
        Without this, a single Redis blip would permanently kill real-time updates.
        """
        backoff = 1
        while True:
            try:
                redis_client = await get_redis()
                pubsub = redis_client.pubsub()
                await pubsub.subscribe("classroom_updates")
                logger.info("WebSocket Manager started listening to Redis PubSub 'classroom_updates'")
                backoff = 1  # Reset backoff on successful connection

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        classroom_id = data.get("classroom_id")
                        payload = data.get("payload")
                        if classroom_id and payload:
                            logger.info(f"[REDIS] Broadcasting: {payload['type']} to {classroom_id}")
                            await self.broadcast_to_classroom(classroom_id, payload)

            except Exception as e:
                logger.error(f"[REDIS] PubSub listener error: {e} — reconnecting in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Exponential backoff, cap at 30s
            finally:
                try:
                    await pubsub.unsubscribe("classroom_updates")
                except Exception:
                    pass

    async def publish_update(self, classroom_id: str, payload: dict):
        """Utility to publish an update to Redis (accessible from any process)."""
        try:
            redis_client = await get_redis()
            message = {
                "classroom_id": classroom_id,
                "payload": payload
            }
            await redis_client.publish("classroom_updates", json.dumps(message))
        except Exception as e:
            # Redis is optional for real-time — don't crash the request
            logger.warning("[publish_update] Redis publish failed (non-fatal): %s", e)

manager = ConnectionManager()
