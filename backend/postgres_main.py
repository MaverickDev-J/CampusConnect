"""Staged PostgreSQL API; mount migrated routes only until cutover is verified.

Run: python postgres_main.py (port 8001)
Requires the non-owner runtime DATABASE_URL and applied Alembic migrations.
"""
from contextlib import asynccontextmanager
from functools import partial
import os
import jwt
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from api.dependencies import get_current_user, oauth2_scheme
from api.routers import auth, classroom
from core.security import decode_access_token
from core.config import settings
from database.postgres import create_session_factory
from repositories.accounts import PostgresAccounts
from repositories.classrooms import PostgresClassrooms
from repositories.files import PostgresFiles
from api.routers import postgres_files
from api.routers import postgres_chat
from api.routers import postgres_campus
from api.routers import postgres_socket
from redis.asyncio import Redis
from api.services.campus_actions import CampusActions
from repositories.chat import PostgresChat
from api.agent.postgres_graph import PostgresRag, GeminiAnswer
from api.agent.nodes import router_node
from api.services.retrieval.embeddings import GeminiEmbeddings
from api.services.retrieval.ranking import GeminiReranker
from google import genai
from api.services.campus_documents import CampusDocuments
from api.agent.faculty_workflow import FacultyWorkflow, GeminiDraftGenerator
from api.routers import workflows
from mcp_server.server import create_mcp
from mcp_server.client import McpDocumentsClient
from core.gemini_budget import ProjectBudget, BudgetedGemini
from api.services.answer_cache import AnswerCache
from api.routers import quality
from api.routers import postgres_admin,postgres_demo


def create_app(database_url=None, *, storage_root=None, redis_url=None):
    origins = [value.strip().rstrip('/') for value in os.getenv('CORS_ORIGINS',
        ','.join(f'http://{host}:{port}' for host in ('localhost','127.0.0.1') for port in (3000,3001))).split(',') if value.strip()]
    if not origins or '*' in origins or any(not value.startswith(('http://','https://')) for value in origins):
        raise ValueError('CORS_ORIGINS must contain explicit HTTP origins')
    @asynccontextmanager
    async def lifespan(app):
        url = database_url or os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required for the PostgreSQL API")
        if len(settings.JWT_SECRET) < 32 or settings.JWT_SECRET in {"super-secret-change-me", "changeme"}:
            raise RuntimeError("A strong JWT_SECRET is required")
        engine, factory = create_session_factory(url)
        clients = {}
        try:
            async with engine.connect() as connection:
                role = (await connection.execute(text("""SELECT r.rolsuper OR r.rolbypassrls OR
                    EXISTS (SELECT 1 FROM pg_tables t WHERE t.schemaname='public' AND t.tableowner=current_user)
                    FROM pg_roles r WHERE r.rolname=current_user"""))).scalar_one()
                if role:
                    raise RuntimeError("PostgreSQL runtime must be a non-owner role without RLS bypass")
                version = (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
                if version != "010_admin_demo":
                    raise RuntimeError("Apply the expected database migrations before starting")
            app.state.accounts = PostgresAccounts(factory)
            app.state.classrooms = PostgresClassrooms(factory)
            app.state.files = PostgresFiles(factory)
            app.state.storage_root = Path(storage_root or os.getenv("STORAGE_DIR", "storage")).resolve()
            def provider(*names):
                raw = next((os.environ[name] for name in names if os.getenv(name)),None)
                if not raw:
                    return None
                key=raw.split(',')[0].strip()
                if key not in clients:
                    clients[key]=genai.Client(api_key=key)
                return clients[key]
            query_client=provider('GEMINI_CHAT_KEYS','GEMINI_API_KEYS','GEMINI_API_KEY')
            retrieval_client=provider('GEMINI_INGESTION_KEYS','GEMINI_API_KEYS','GEMINI_API_KEY','GEMINI_CHAT_KEYS')
            app.state.chat = PostgresChat(factory)
            app.state.actions = CampusActions(factory)
            budget = app.state.ai_budget = ProjectBudget(factory)
            app.state.answer_cache=AnswerCache(factory) if os.getenv('AI_ANSWER_CACHE','true').lower()=='true' else None
            app.state.rag = PostgresRag(factory, GeminiEmbeddings(retrieval_client, budget=budget),
                GeminiReranker(BudgetedGemini(retrieval_client, budget, 'rerank')) if retrieval_client else None,
                route=partial(router_node,client=query_client),budget=budget,cache=app.state.answer_cache)
            app.state.answer = GeminiAnswer(BudgetedGemini(query_client, budget, 'answer') if query_client else None)
            app.state.documents = CampusDocuments(factory, app.state.rag, app.state.files)
            app.state.workflows = FacultyWorkflow(factory, McpDocumentsClient(app), app.state.actions,
                GeminiDraftGenerator(BudgetedGemini(query_client, budget, 'draft') if query_client else None))
            app.state.ws_redis = Redis.from_url(redis_url or settings.REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
            app.state.ws_origins = origins
            async with mcp_app.lifespan(app):
                yield
        finally:
            if hasattr(app.state,'ws_redis'):
                await app.state.ws_redis.aclose()
            for client in clients.values():
                await client.aio.aclose()
            await engine.dispose()

    app = FastAPI(title="CampusConnect PostgreSQL staging API", lifespan=lifespan)
    mcp = create_mcp(app)
    mcp_app = mcp.http_app(path='/', stateless_http=True, json_response=True)
    app.mount('/mcp', mcp_app)
    app.add_middleware(CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True, allow_methods=["GET","POST","PUT","PATCH","DELETE"],
        allow_headers=["Authorization","Content-Type","Idempotency-Key"])

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
    app.include_router(postgres_files.router)
    app.include_router(postgres_chat.router)
    app.include_router(postgres_campus.router)
    app.include_router(postgres_socket.router)
    app.include_router(workflows.router)
    app.include_router(quality.router)
    app.include_router(postgres_admin.router)
    app.include_router(postgres_demo.router)

    @app.get("/health")
    async def health():
        async with app.state.accounts.factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "checks": {"postgresql": "ok"}, "migration_stage": "010_admin_demo"}

    return app


app = create_app()

if __name__ == "__main__":
    import asyncio
    import sys
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="127.0.0.1", port=8001, loop="asyncio")
