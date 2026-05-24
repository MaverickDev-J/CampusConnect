"""
celery_app.py — CampusMind Celery Worker Configuration
=======================================================
Broker + Backend: Redis
Worker: Single process (solo pool) for safe Docling/PyMuPDF usage
Task retry, time limits, and serialization are configured here.
"""

import os
from celery import Celery
from celery.signals import task_failure, task_retry, task_success

REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
REDIS_RESULT_URL = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

celery_app = Celery(
    "campusmind_worker",
    broker=REDIS_URL,
    backend=REDIS_RESULT_URL,
    include=["api.services.ingestion"],
)

celery_app.conf.update(
    # ── Serialization ─────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Timezone ──────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,

    # ── Worker concurrency ────────────────────────────────────────
    # Keep at 1 (solo pool) — Docling loads large ML models into RAM.
    # Running multiple workers on the same machine would cause OOM errors.
    worker_concurrency=1,
    worker_prefetch_multiplier=1,       # Don't grab next task until current is done

    # ── Task time limits ──────────────────────────────────────────
    # These are defaults; individual tasks can override with their own limits.
    task_soft_time_limit=840,           # 14 min SIGTERM warning
    task_time_limit=900,                # 15 min hard SIGKILL

    # ── Result TTL ────────────────────────────────────────────────
    result_expires=3600,                # Keep task results in Redis for 1 hour

    # ── Retry ─────────────────────────────────────────────────────
    task_acks_late=True,                # Only ack task AFTER it completes (safe retries)
    task_reject_on_worker_lost=True,    # Re-queue if worker dies mid-task

    # ── Monitoring ────────────────────────────────────────────────
    worker_send_task_events=True,       # Enable for Flower monitoring
    task_send_sent_event=True,
)


# ── Logging hooks (optional) ─────────────────────────────────────────

import logging
logger = logging.getLogger(__name__)

@task_failure.connect
def on_task_failure(task_id, exception, args, kwargs, traceback, einfo, **kw):
    logger.error(
        "[Celery] Task FAILED task_id=%s file_id=%s error=%s",
        task_id,
        args[0] if args else "?",
        str(exception)[:200],
    )

@task_retry.connect
def on_task_retry(request, reason, einfo, **kw):
    task_name = getattr(request, "task", "unknown")
    retries = getattr(request, "retries", 0)
    max_retries = getattr(request, "max_retries", "?")
    
    logger.warning(
        "[Celery] Task RETRYING task_id=%s retries=%s/%s reason=%s",
        request.id,
        retries,
        max_retries,
        str(reason)[:100],
    )

@task_success.connect
def on_task_success(result, **kw):
    logger.info("[Celery] Task SUCCESS result=%s", result)
