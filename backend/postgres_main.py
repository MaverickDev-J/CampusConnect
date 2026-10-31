"""Staged PostgreSQL API; mount migrated routes only until cutover is verified.

Run: python postgres_main.py (port 8001)
Requires the non-owner runtime DATABASE_URL and applied Alembic migrations.
"""
from contextlib import asynccontextmanager
import os
import jwt

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from api.dependencies import get_current_user, oauth2_scheme
from api.routers import auth, classroom
from core.security import decode_access_token
from core.config import settings
from database.postgres import create_session_factory
from repositories.accounts import PostgresAccounts
from repositories.classrooms import PostgresClassrooms


def create_app(database_url=None):
    @asynccontextmanager
    async def lifespan(app):
        url = database_url or os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required for the PostgreSQL API")
        if len(settings.JWT_SECRET) < 32 or settings.JWT_SECRET in {"super-secret-change-me", "changeme"}:
            raise RuntimeError("A strong JWT_SECRET is required")
        engine, factory = create_session_factory(url)
        try:
            async with engine.connect() as connection:
                role = (await connection.execute(text("""SELECT r.rolsuper OR r.rolbypassrls OR
                    EXISTS (SELECT 1 FROM pg_tables t WHERE t.schemaname='public' AND t.tableowner=current_user)
                    FROM pg_roles r WHERE r.rolname=current_user"""))).scalar_one()
                if role:
                    raise RuntimeError("PostgreSQL runtime must be a non-owner role without RLS bypass")
                version = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
                if version != "003_accounts":
                    raise RuntimeError("Apply the expected database migrations before starting")
            app.state.accounts = PostgresAccounts(factory)
            app.state.classrooms = PostgresClassrooms(factory)
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="CampusConnect PostgreSQL staging API", lifespan=lifespan)

    async def current_user(token=Depends(oauth2_scheme)):
        try:
            user_id = decode_access_token(token).get("user_id")
            user = await app.state.accounts.by_id(user_id) if user_id else None
        except (jwt.InvalidTokenError, ValueError, TypeError):
            user = None
        if not user:
            raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
        return user

    app.dependency_overrides[get_current_user] = current_user
    app.include_router(auth.router)
    app.include_router(classroom.router)

    @app.get("/health")
    async def health():
        async with app.state.accounts.factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "checks": {"postgresql": "ok"}, "migration_stage": "accounts_classrooms"}

    return app


app = create_app()

if __name__ == "__main__":
    import asyncio
    import sys
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="127.0.0.1", port=8001, loop="asyncio")
