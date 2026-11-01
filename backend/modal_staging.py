"""PostgreSQL staging deployment. Run Modal commands from this directory."""
import os
from pathlib import Path

import modal

ROOT = Path(__file__).parent
app = modal.App('campusconnect-postgres')
volume = modal.Volume.from_name('campusconnect-postgres-uploads', create_if_missing=True, version=2)
legacy_secret = modal.Secret.from_name('campusconnect-secrets')
api_secrets = [legacy_secret, modal.Secret.from_name('campusconnect-postgres-api',
    required_keys=['DATABASE_URL','JWT_SECRET','CORS_ORIGINS'])]
worker_secrets = [legacy_secret, modal.Secret.from_name('campusconnect-postgres-worker',
    required_keys=['DATABASE_URL'])]
image = (modal.Image.debian_slim(python_version='3.11')
    .uv_sync(str(ROOT), frozen=True, uv_version='0.11.16')
    .env({'STORAGE_DIR':'/data/storage','DEMO_ENABLED':'false','PYTHONUNBUFFERED':'1'})
    .add_local_python_source('api','core','database','models','repositories','mcp_server','postgres_main'))


@app.function(image=image, secrets=worker_secrets, volumes={'/data':volume},
              max_containers=1, scaledown_window=10, timeout=900, memory=1024,region='ap')
async def ingest():
    from google import genai
    from api.services.postgres_ingestion import IngestionWorker
    from api.services.retrieval.embeddings import GeminiEmbeddings
    from core.gemini_budget import ProjectBudget
    from core.hosted_runtime import drain
    from database.postgres import create_session_factory

    await volume.reload.aio()
    engine,factory=create_session_factory(os.environ['DATABASE_URL'],pool_size=2)
    key=next((os.environ[name].split(',')[0].strip() for name in
        ('GEMINI_INGESTION_KEYS','GEMINI_API_KEY','GEMINI_API_KEYS') if os.getenv(name)),None)
    if not key:
        raise RuntimeError('An ingestion API key is required')
    client=genai.Client(api_key=key)
    budget=ProjectBudget(factory)
    try:
        worker=IngestionWorker(factory,GeminiEmbeddings(client,budget=budget),'/data/storage',budget=budget)
        return await drain(worker,max_rounds=4,max_seconds=180)
    finally:
        await client.aio.aclose()
        await engine.dispose()


@app.function(image=image, secrets=worker_secrets, volumes={'/data':volume},
              max_containers=1, scaledown_window=10, timeout=120, memory=512,region='ap')
async def deliver():
    import json
    from redis.asyncio import Redis
    from api.services.campus_outbox import CampusOutbox
    from api.services.storage_cleanup import StorageCleanup
    from core.hosted_runtime import drain
    from database.postgres import create_session_factory

    await volume.reload.aio()
    engine,factory=create_session_factory(os.environ['DATABASE_URL'],pool_size=1)
    redis=Redis.from_url(os.environ['REDIS_URL'],socket_connect_timeout=5,socket_timeout=5)
    async def publish(classroom,payload):
        await redis.publish('classroom_updates',json.dumps({'classroom_id':classroom,'payload':payload}))
    try:
        return await drain(CampusOutbox(factory,publish),
            StorageCleanup(factory,'/data/storage',persist=volume.commit.aio))
    finally:
        await redis.aclose()
        await engine.dispose()


@app.function(image=image, secrets=api_secrets, volumes={'/data':volume},
              max_containers=2, scaledown_window=30, timeout=300, memory=1024,region='ap')
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def fastapi_app():
    from postgres_main import create_app
    from core.hosted_runtime import VolumeRequests,WakeJobs

    web=create_app()
    web.state.persist_upload=volume.commit.aio
    async def wake(kind):
        # Polls can resume quota-deferred ingestion without a minute-by-minute
        # database cron. PostgreSQL leases make duplicate invocations safe.
        redis=web.state.ws_redis
        ticket=f'postgres-staging:wake:{kind}'
        if await redis.set(ticket,'1',nx=True,ex=60 if kind=='ingestion' else 2):
            try:
                await (ingest if kind=='ingestion' else deliver).spawn.aio()
            except BaseException:
                await redis.delete(ticket)
                raise
    web.add_middleware(VolumeRequests,reload=volume.reload.aio)
    web.add_middleware(WakeJobs,wake=wake)
    return web


@app.function(image=image, schedule=modal.Cron('17 * * * *'),timeout=30,memory=256)
async def rescue():
    """Recover a missed enqueue or expired worker lease, with bounded idle cost."""
    await ingest.spawn.aio()
    await deliver.spawn.aio()


@app.function(image=image,secrets=api_secrets,volumes={'/data':volume},timeout=90,memory=512,region='ap')
async def diagnose():
    """Return connectivity booleans and dependency versions, never credentials."""
    import importlib.metadata
    import importlib.util
    from redis.asyncio import Redis
    from sqlalchemy import text
    from database.postgres import create_session_factory
    await volume.reload.aio()
    engine,factory=create_session_factory(os.environ['DATABASE_URL'],pool_size=1)
    redis=Redis.from_url(os.environ['REDIS_URL'],socket_connect_timeout=5,socket_timeout=5)
    try:
        async with factory() as session:
            revision=(await session.execute(text('SELECT version_num FROM alembic_version'))).scalar_one()
        marker=Path('/data/storage/.deployment-probe')
        marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text('persistent upload volume',encoding='utf-8')
        await volume.commit.aio()
        await volume.reload.aio()
        durable=marker.read_text(encoding='utf-8')=='persistent upload volume'
        marker.unlink()
        await volume.commit.aio()
        packages={name:importlib.metadata.version(name) for name in ('fastapi','fastmcp','google-genai','langgraph','psycopg')}
        return {'revision':revision,'redis':bool(await redis.ping()),'volume':durable,
                'packages':packages,'local_models':any(importlib.util.find_spec(name) is not None for name in ('torch','docling','chromadb'))}
    finally:
        await redis.aclose()
        await engine.dispose()
