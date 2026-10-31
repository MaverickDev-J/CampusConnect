"""
modal_app.py — Serverless FastAPI deployment for CampusConnect on Modal.
Scales to zero when idle ($0 cost).
"""

import os
import modal

# 1. Persistent volume for ChromaDB vector embeddings and uploaded materials
volume = modal.Volume.from_name("campusconnect-data", create_if_missing=True)

# 2. Define the container image with all backend dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.30.0",
        "motor>=3.6.0,<4.0",
        "pymongo>=4.9.0,<4.10",
        "redis>=5.2.0",
        "chromadb>=0.5.3",
        "google-genai>=1.63.0",
        "langgraph>=1.0.8",
        "langchain-core>=1.2.13",
        "langchain-text-splitters>=1.1.0",
        "pymupdf>=1.24.0",
        "pydantic>=2.8.0",
        "pydantic-settings>=2.4.0",
        "pyjwt[crypto]>=2.9.0",
        "passlib[bcrypt]>=1.7.4",
        "python-multipart>=0.0.9",
        "python-dotenv>=1.0.1",
        "aiofiles>=24.1.0",
        "numpy>=1.26.0",
        "slowapi>=0.1.9",
        "email-validator>=2.1.0",
        "pillow>=10.0.0",
        "ddgs>=6.4.0",
        "celery>=5.4.0",
        "sqlalchemy[asyncio]==2.1.6",
        "psycopg[binary,pool]==3.3.6",
        "pgvector==0.5.1",
    )
    .add_local_python_source("api", "core", "database", "models", "repositories", "main")
)

app = modal.App("campusconnect", image=image)


@app.function(
    image=image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("campusconnect-secrets")],
    timeout=600,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    # Set persistent paths for ChromaDB and uploaded files on the Modal volume
    os.environ["CHROMA_PERSIST_DIR"] = "/data/chroma"
    os.environ["STORAGE_DIR"] = "/data/storage"

    from main import app as web_app
    return web_app
