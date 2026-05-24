"""Async Redis client singleton for caching."""
import redis.asyncio as redis
import os
import logging

logger = logging.getLogger(__name__)

# Default Redis URL from environment or fallback to 127.0.0.1 (IPv4)
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

class RedisManager:
    _client: redis.Redis = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        if cls._client is None:
            logger.info(f"Connecting to Redis at {REDIS_URL}")
            cls._client = redis.from_url(REDIS_URL, decode_responses=True)
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.close()
            cls._client = None

async def get_redis():
    return await RedisManager.get_client()
