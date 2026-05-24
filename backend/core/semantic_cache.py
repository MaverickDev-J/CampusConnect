"""
semantic_cache.py — Vector Similarity Cache for LLM Responses
=============================================================

WHY THIS EXISTS:
The old cache used SHA-256 of the query string — "What is Newton's second law?"
and "Explain F=ma" produce different hashes despite being the same question.

This module adds a second cache layer that embeds the query and checks cosine
similarity against the last N cached queries in the same classroom. If a
semantically identical question was asked before, we return the cached response
instead of burning another Gemini API call.

ARCHITECTURE:
  Query → Embed → Cosine search in Redis cache → Hit (>0.93)? Return cached.
                                                  Miss? Run agent → Store.

STORAGE:
  Redis sorted set  `sem_cache:{classroom_id}` — stores JSON entries with
  the query embedding, response text, and source citations.
  Max 200 entries per classroom (FIFO eviction).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import numpy as np

from database.redis import get_redis

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.93   # Cosine similarity above this = cache hit
MAX_CACHE_SIZE = 200          # Max entries per classroom
CACHE_TTL = 86400             # 24 hours in seconds


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(dot / norm)


async def check_semantic_cache(
    query_embedding: list[float],
    classroom_id: str,
) -> Optional[dict]:
    """
    Check if a semantically similar query has been cached.

    Args:
        query_embedding: The embedding vector of the incoming query.
        classroom_id:    Scope key (different classrooms = different caches).

    Returns:
        dict with 'content' and 'sources' if cache hit, else None.
    """
    if not query_embedding:
        return None

    cache_key = f"sem_cache:{classroom_id or 'global'}"

    try:
        redis = await get_redis()
        entries_raw = await redis.lrange(cache_key, 0, MAX_CACHE_SIZE - 1)

        if not entries_raw:
            return None

        best_score = 0.0
        best_entry = None

        for raw in entries_raw:
            entry = json.loads(raw)
            cached_embedding = entry.get("embedding")
            if not cached_embedding:
                continue

            score = _cosine_similarity(query_embedding, cached_embedding)

            if score > best_score:
                best_score = score
                best_entry = entry

        if best_score >= SIMILARITY_THRESHOLD and best_entry:
            logger.info(
                "[SemanticCache] HIT score=%.4f query_preview='%s' → cached_query='%s'",
                best_score,
                "",  # We don't have the query text here, just embedding
                best_entry.get("query", "")[:60],
            )
            return {
                "content": best_entry["content"],
                "sources": best_entry.get("sources", []),
                "cache_score": best_score,
            }

        logger.debug("[SemanticCache] MISS best_score=%.4f (threshold=%.2f)", best_score, SIMILARITY_THRESHOLD)
        return None

    except Exception as e:
        logger.warning("[SemanticCache] Check failed: %s", e)
        return None


async def store_in_semantic_cache(
    query_text: str,
    query_embedding: list[float],
    response_content: str,
    sources: list,
    classroom_id: str,
) -> None:
    """
    Store a query-response pair in the semantic cache.

    Args:
        query_text:       Original query string (for debugging/logging).
        query_embedding:  The embedding vector of the query.
        response_content: The full AI response text.
        sources:          List of source citations.
        classroom_id:     Scope key.
    """
    if not query_embedding or not response_content:
        return

    cache_key = f"sem_cache:{classroom_id or 'global'}"

    entry = {
        "query": query_text[:200],  # Truncated for storage efficiency
        "embedding": query_embedding,
        "content": response_content,
        "sources": sources,
        "stored_at": time.time(),
    }

    try:
        redis = await get_redis()
        # Push to the left (newest first), trim to max size
        await redis.lpush(cache_key, json.dumps(entry))
        await redis.ltrim(cache_key, 0, MAX_CACHE_SIZE - 1)
        # Set TTL on the entire list
        await redis.expire(cache_key, CACHE_TTL)

        logger.info("[SemanticCache] Stored entry for classroom=%s query='%s'", classroom_id, query_text[:60])

    except Exception as e:
        logger.warning("[SemanticCache] Store failed: %s", e)
