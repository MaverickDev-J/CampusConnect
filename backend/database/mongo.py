"""Motor (async MongoDB) client singleton."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from core.config import settings

client: AsyncIOMotorClient = None  # type: ignore[assignment]
db: AsyncIOMotorDatabase = None  # type: ignore[assignment]


async def connect_db() -> None:
    """Initialise the Motor client and select the database."""
    global client, db
    client = AsyncIOMotorClient(
        settings.MONGO_URI,
        # Connection pool settings
        maxPoolSize=20,
        minPoolSize=2,
        # Timeout settings (prevent silent hangs when Docker is starting)
        connectTimeoutMS=5000,
        serverSelectionTimeoutMS=5000,
        socketTimeoutMS=10000,
    )
    db = client[settings.MONGO_DB]


async def close_db() -> None:
    """Gracefully close the Motor client."""
    global client
    if client:
        client.close()


def get_db() -> AsyncIOMotorDatabase:
    """Return the current database handle."""
    return db
