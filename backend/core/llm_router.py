"""
llm_router.py — Production-grade Gemini Key Rotation & Isolated Model Pools
============================================================================

Three independent key pools that prevent cross-contamination of rate limits:

  POOL 1 — ROUTER_KEYS    : Fast classification. Cheap, lightweight models.
  POOL 2 — CHAT_KEYS      : Chat synthesis & embeddings. Quality + stability.
  POOL 3 — INGESTION_KEYS : PDF extraction. Multimodal-capable models.

Each pool reads from its own env var, then falls back to the shared pool:
  GEMINI_ROUTER_KEYS      → GEMINI_API_KEYS → GEMINI_API_KEY
  GEMINI_CHAT_KEYS        → GEMINI_API_KEYS → GEMINI_API_KEY
  GEMINI_INGESTION_KEYS   → GEMINI_API_KEYS → GEMINI_API_KEY

This means you can run with a single key (all pools fall back to it),
or distribute load across multiple keys per pool.

MODEL CHAINS (ordered: best first, most stable last):
  ROUTER_CHAIN     : [gemini-2.0-flash-lite, gemini-1.5-flash-8b, gemini-1.5-flash]
  CHAT_CHAIN       : [gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash]
  INGESTION_CHAIN  : [gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash]

Note: gemini-2.5-flash is experimental — excluded from all primary chains.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load .env BEFORE os.getenv() is called at module import time.
# Without this, Celery workers start with empty env vars because
# the .env is not yet loaded when GeminiKeyManager is instantiated.
load_dotenv()

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Key Manager
# ══════════════════════════════════════════════════════════════════════

class GeminiKeyManager:
    """
    Manages a named pool of Gemini API keys with per-key health tracking.
    Keys that return 429/503 are put in a 60-second penalty box.
    """

    def __init__(self, pool_name: str, env_vars: List[str]):
        """
        Args:
            pool_name:  Human-readable name for logging (e.g. "ROUTER").
            env_vars:   List of env var names to try in order. The first non-empty one is used.
                        Keys should be comma-separated within each var.
        """
        self.pool_name = pool_name
        self.keys: List[str] = []

        for env_var in env_vars:
            raw = os.getenv(env_var, "").strip()
            if raw:
                self.keys = [k.strip() for k in raw.split(",") if k.strip()]
                logger.info("[%s pool] Loaded %d key(s) from %s", pool_name, len(self.keys), env_var)
                break

        if not self.keys:
            logger.error(
                "[%s pool] No Gemini API keys found! Checked env vars: %s",
                pool_name,
                ", ".join(env_vars),
            )

        self._unhealthy: dict[int, float] = {}  # {key_index: expiry_timestamp}
        self._idx = 0

    # ── Public API ──────────────────────────────────────────────────

    def get_client(self) -> tuple[genai.Client, str]:
        """Return a healthy (client, key) pair. Rotates round-robin, skips penalised keys."""
        if not self.keys:
            raise RuntimeError(f"[{self.pool_name}] No Gemini keys configured")

        now = time.time()
        # Expire stale penalties
        self._unhealthy = {i: exp for i, exp in self._unhealthy.items() if exp > now}

        for _ in range(len(self.keys)):
            idx = self._idx % len(self.keys)
            self._idx += 1
            if idx not in self._unhealthy:
                key = self.keys[idx]
                return genai.Client(api_key=key), key

        # All keys in penalty box — back off and retry
        wait = 5
        logger.warning("[%s pool] All keys in penalty box. Sleeping %ds...", self.pool_name, wait)
        time.sleep(wait)
        return self.get_client()

    def mark_unhealthy(self, key: str, duration: int = 60) -> None:
        """Put a key in the penalty box for `duration` seconds."""
        try:
            idx = self.keys.index(key)
            self._unhealthy[idx] = time.time() + duration
            logger.warning(
                "[%s pool] Key ...%s penalised for %ds", self.pool_name, key[-4:], duration
            )
        except ValueError:
            pass

    @property
    def has_keys(self) -> bool:
        return bool(self.keys)


# ══════════════════════════════════════════════════════════════════════
# Singleton Key Pools
# ══════════════════════════════════════════════════════════════════════

# Pool for query routing (classifier — fast, cheap)
router_key_manager = GeminiKeyManager(
    pool_name="ROUTER",
    env_vars=["GEMINI_ROUTER_KEYS", "GEMINI_API_KEYS", "GEMINI_API_KEY"],
)

# Pool for chat synthesis and query embeddings
chat_key_manager = GeminiKeyManager(
    pool_name="CHAT",
    env_vars=["GEMINI_CHAT_KEYS", "GEMINI_API_KEYS", "GEMINI_API_KEY"],
)

# Pool for PDF/image ingestion (multimodal File API calls)
ingestion_key_manager = GeminiKeyManager(
    pool_name="INGESTION",
    env_vars=["GEMINI_INGESTION_KEYS", "GEMINI_API_KEYS", "GEMINI_API_KEY"],
)

# Backwards-compat alias — code that imported `key_manager` still works
key_manager = chat_key_manager


# ══════════════════════════════════════════════════════════════════════
# Model Chains
# ══════════════════════════════════════════════════════════════════════

# Lightweight, deterministic. Used by router_node.
ROUTER_MODEL_CHAIN: List[str] = [
    "gemini-2.5-flash-lite",   # Fastest free-tier model, best at structured JSON
    "gemini-2.5-flash",        # High-quota, reliable fallback
    "gemini-2.5-flash-lite",   # Safe duplicate fallback
]

# ─────────────────────────────────────────────────────────────
# CHAT_MODEL_CHAIN → Final answer generation (synthesis_node)
# Balanced quality + speed
# ─────────────────────────────────────────────────────────────
CHAT_MODEL_CHAIN: List[str] = [
    "gemini-2.5-flash",        # Primary: best quality/speed balance on free tier
    "gemini-1.5-pro",          # Higher reasoning quality when Flash is rate-limited
    "gemini-2.5-flash",        # Safe duplicate fallback
]

# ─────────────────────────────────────────────────────────────
# INGESTION_MODEL_CHAIN → PDF/Image parsing (multimodal)
# Used by Celery ingestion task + Gemini File API
# ─────────────────────────────────────────────────────────────
INGESTION_MODEL_CHAIN: List[str] = [
    "gemini-2.5-flash",        # Strongest free-tier multimodal (tables, diagrams, formulas, scans)
    "gemini-1.5-pro",          # Proven high-quality fallback
    "gemini-2.5-flash",        # Safe duplicate fallback
]

# ══════════════════════════════════════════════════════════════════════
# Core Callable
# ══════════════════════════════════════════════════════════════════════

async def call_gemini_with_fallback(
    model_chain: List[str],
    contents: Any,
    config: Optional[types.GenerateContentConfig] = None,
    system_instruction: Optional[str] = None,
    key_pool: Optional[GeminiKeyManager] = None,
    forced_client: Optional[genai.Client] = None,
) -> Any:
    """
    Call Gemini with automatic model fallback and key rotation.

    Args:
        model_chain:       Ordered list of model names to try.
        contents:          Prompt contents (str, list, etc.).
        config:            GenerateContentConfig (optional).
        system_instruction: System prompt override (optional).
        key_pool:          Which key manager to use. Defaults to chat_key_manager.

    Returns:
        The first successful GenerateContentResponse.

    Raises:
        RuntimeError if all models in the chain fail across all keys.
    """
    pool = key_pool or chat_key_manager

    if not pool.has_keys:
        raise RuntimeError(f"[{pool.pool_name}] No API keys configured")

    for model_name in model_chain:
        # If a client is forced (e.g. for File API), we only attempt once with that client.
        attempts = 1 if forced_client else max(len(pool.keys), 1)
        for attempt in range(attempts):
            if forced_client:
                client = forced_client
                key = "forced"
            else:
                client, key = pool.get_client()

            # Build config if not provided
            effective_config = config
            if effective_config is None:
                effective_config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.4,
                )
            elif system_instruction:
                # Inject system instruction into existing config object
                effective_config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=getattr(effective_config, "temperature", 0.4),
                    max_output_tokens=getattr(effective_config, "max_output_tokens", None),
                    response_mime_type=getattr(effective_config, "response_mime_type", None),
                )

            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=effective_config,
                )
                logger.debug(
                    "[%s pool] Success: model=%s key=...%s",
                    pool.pool_name, model_name, key[-4:],
                )
                return response

            except Exception as e:
                err = str(e)
                is_transient = any(
                    code in err for code in ("503", "429", "RESOURCE_EXHAUSTED", "Service Unavailable")
                )
                is_model_not_found = "404" in err and "models/" in err

                if is_transient:
                    logger.warning(
                        "[%s pool] Transient error on %s key=...%s (attempt %d/%d): %s",
                        pool.pool_name, model_name, key[-4:], attempt + 1, attempts, err[:120],
                    )
                    pool.mark_unhealthy(key, duration=90)
                    await asyncio.sleep(min(2 ** attempt, 10))  # Exponential backoff up to 10s
                    continue

                elif is_model_not_found:
                    logger.warning(
                        "[%s pool] Model %s not found (404). Trying next model.",
                        pool.pool_name, model_name,
                    )
                    break  # Move immediately to next model in chain

                else:
                    # Permanent error (auth, bad content, etc.) — raise immediately
                    logger.error(
                        "[%s pool] Permanent error on %s: %s",
                        pool.pool_name, model_name, err[:200],
                    )
                    raise

    raise RuntimeError(
        f"[{pool.pool_name}] All models {model_chain} failed after exhausting all keys."
    )
