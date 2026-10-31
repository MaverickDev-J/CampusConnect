"""PostgreSQL sessions. This module does not switch legacy routes at import time."""
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def create_session_factory(url: str, *, pool_size=3, max_overflow=0):
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_async_engine(url, pool_size=pool_size, max_overflow=max_overflow, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def principal_session(factory, user_id: str):
    if not user_id:
        raise ValueError("Authenticated user ID required")
    async with factory() as session:
        async with session.begin():
            # The third argument makes identity local to the transaction.
            await session.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user_id})
            yield session
