# ══════════════════════════════════════════════════════════════
# CampusConnect Backend — Production Dockerfile
# ══════════════════════════════════════════════════════════════
# Multi-stage build: install deps → copy code → run with gunicorn
# Same image used for: backend API, Celery worker, and Flower

FROM python:3.11-slim AS base

# System deps for PyMuPDF, Pillow, and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# ── Install dependencies (cached layer) ────────────────────
COPY pyproject.toml ./
# Add numpy for semantic cache
RUN uv pip install --system --no-cache -r pyproject.toml && \
    uv pip install --system --no-cache gunicorn numpy

# ── Copy application code ──────────────────────────────────
COPY . .

# Create storage directories
RUN mkdir -p storage/uploads/pdfs storage/uploads/images storage/temp

# ── Health check ───────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Default: run the API server with Gunicorn + Uvicorn workers
CMD ["gunicorn", "main:app", \
     "-w", "2", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]
