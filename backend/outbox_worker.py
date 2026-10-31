"""Deliver committed campus updates to Redis using a separate restricted worker."""
import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
from redis.asyncio import Redis
from api.services.campus_outbox import CampusOutbox
from api.services.storage_cleanup import StorageCleanup
from database.postgres import create_session_factory


async def main():
    load_dotenv()
    engine, factory = create_session_factory(os.environ['DATABASE_URL'])
    redis = Redis.from_url(os.environ['REDIS_URL'], socket_timeout=5, socket_connect_timeout=5)
    async def publish(classroom, payload):
        await redis.publish('classroom_updates', json.dumps({'classroom_id':classroom, 'payload':payload}))
    dispatcher = CampusOutbox(factory, publish)
    cleanup = StorageCleanup(factory, os.getenv('STORAGE_DIR','storage'))
    try:
        while True:
            try:
                delivered = await dispatcher.run_once()
                cleaned = await cleanup.run_once()
                if not delivered and not cleaned:
                    await asyncio.sleep(2)
            except Exception:
                logging.warning('Campus outbox unavailable; retrying')
                await asyncio.sleep(5)
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
