"""
ingestion.py — 3-Tier PDF Extraction + Celery Background Ingestion
===================================================================

EXTRACTION TIERS (in order of quality and preference):

  TIER 1 — Gemini File API  (multimodal, handles tables/diagrams/equations)
      - Uses INGESTION key pool with INGESTION_MODEL_CHAIN
      - Retries up to 3 times with key rotation on 429/503
      - Typical latency: 10-90 seconds depending on file size

  TIER 2 — Docling  (local, free, structured text + basic tables)
      - CPU-based, no API key needed
      - Good for well-formatted PDFs without complex visuals
      - Typical latency: 30-120 seconds (heavy model)

  TIER 3 — PyMuPDF  (local, free, text-only, fastest)
      - No table/image/equation understanding
      - Used as last resort only
      - File is flagged in metadata: extraction_method = "pymupdf_text_only"
      - Students are warned in the UI that content may be incomplete

CELERY TASK:
  - Retries up to 3 times if any tier fails (Celery-level retry, not just tier retry)
  - Hard time limit: 15 minutes per task
  - Uses the INGESTION key pool (never touches ROUTER or CHAT pools)
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from core.celery_app import celery_app
from core.llm_router import (
    INGESTION_MODEL_CHAIN,
    call_gemini_with_fallback,
    ingestion_key_manager,
)
from core.websocket import manager
from database.chroma import get_chroma_collection
from database.mongo import get_db

load_dotenv()

logger = logging.getLogger(__name__)

EMBED_MODEL = "models/gemini-embedding-001"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
EMBED_BATCH_SIZE = 50   # Reduced from 100 to reduce 429 risk


# ══════════════════════════════════════════════════════════════════════
# TIER 1: Gemini File API
# ══════════════════════════════════════════════════════════════════════

async def _extract_with_gemini(file_path: str) -> str:
    """
    Upload file to Gemini File API and extract rich text (tables, equations, diagrams).
    Uses INGESTION key pool with INGESTION_MODEL_CHAIN and key rotation.
    """
    client, key = ingestion_key_manager.get_client()
    logger.info("[Tier 1] Uploading %s to Gemini File API...", file_path)

    # Upload the file
    def _upload():
        return client.files.upload(file=file_path)

    try:
        gemini_file = await asyncio.to_thread(_upload)
    except Exception as e:
        logger.error("[Tier 1] Upload failed: %s", e)
        raise

    try:
        logger.info("[Tier 1] Extracting content via model chain: %s", INGESTION_MODEL_CHAIN)
        prompt = (
            "You are a precise document parser. Extract ALL content from this document:\n"
            "1. Text: Preserve the reading order and section hierarchy\n"
            "2. Tables: Convert to clean Markdown table format\n"
            "3. Mathematical equations: Render in LaTeX format ($...$ inline, $$...$$ block)\n"
            "4. Diagrams/Figures: Provide a brief textual description in [Figure: ...] brackets\n"
            "5. Code: Wrap in ```language ... ``` blocks\n\n"
            "Output ONLY the extracted content. No preamble, no explanations."
        )

        response = await call_gemini_with_fallback(
            model_chain=INGESTION_MODEL_CHAIN,
            contents=[gemini_file, prompt],
            key_pool=ingestion_key_manager,
            forced_client=client,
        )

        text = response.text
        if not text or not text.strip():
            raise RuntimeError("Gemini returned empty text for this file")

        logger.info("[Tier 1] Extraction successful: %d characters", len(text))
        return text

    finally:
        # Always clean up the uploaded file to avoid Gemini storage charges
        def _delete():
            try:
                client.files.delete(name=gemini_file.name)
            except Exception as del_err:
                logger.warning("[Tier 1] Failed to delete Gemini file %s: %s", gemini_file.name, del_err)
        await asyncio.to_thread(_delete)


# ══════════════════════════════════════════════════════════════════════
# TIER 2: Docling (local, free, structured)
# ══════════════════════════════════════════════════════════════════════

async def _extract_with_docling(file_path: str) -> str:
    """
    Extract text using Docling (local). Handles structured PDFs with tables.
    Runs in a thread to avoid blocking the async event loop.
    """
    logger.info("[Tier 2] Extracting with Docling: %s", file_path)

    def _run_docling() -> str:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(file_path)
        return result.document.export_to_markdown()

    try:
        text = await asyncio.to_thread(_run_docling)
        if not text or not text.strip():
            raise RuntimeError("Docling returned empty text")
        logger.info("[Tier 2] Docling extraction successful: %d characters", len(text))
        return text
    except ImportError:
        raise RuntimeError("Docling is not installed. Add 'docling' to pyproject.toml dependencies.")
    except Exception as e:
        logger.error("[Tier 2] Docling failed: %s", e)
        raise


# ══════════════════════════════════════════════════════════════════════
# TIER 3: PyMuPDF (local, free, text-only fallback)
# ══════════════════════════════════════════════════════════════════════

async def _extract_with_pymupdf(file_path: str) -> str:
    """
    Last-resort text extraction using PyMuPDF (fitz).
    No table or image understanding — plain text only.
    """
    logger.warning("[Tier 3] Using PyMuPDF (text-only). Tables/images may be missing: %s", file_path)

    def _run_pymupdf() -> str:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        pages = []
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text("text")
            if page_text.strip():
                pages.append(f"[Page {page_num}]\n{page_text}")
        doc.close()
        return "\n\n".join(pages)

    try:
        text = await asyncio.to_thread(_run_pymupdf)
        if not text or not text.strip():
            raise RuntimeError("PyMuPDF returned no text — file may be image-only or encrypted")
        logger.info("[Tier 3] PyMuPDF extraction: %d characters", len(text))
        return text
    except ImportError:
        raise RuntimeError("PyMuPDF is not installed. Add 'pymupdf' to pyproject.toml dependencies.")
    except Exception as e:
        logger.error("[Tier 3] PyMuPDF failed: %s", e)
        raise


# ══════════════════════════════════════════════════════════════════════
# Orchestrator: Try all 3 tiers in order
# ══════════════════════════════════════════════════════════════════════

async def _extract_text_tiered(file_path: str, file_type: str) -> tuple[str, str]:
    """
    Try extraction tiers in order. Returns (extracted_text, method_used).

    method_used is one of: "gemini", "docling", "pymupdf_text_only"
    If pymupdf_text_only, the caller should flag the content in metadata.
    """
    errors: list[str] = []

    # Tier 1 — Gemini File API (best quality, multimodal)
    if ingestion_key_manager.has_keys:
        try:
            text = await _extract_with_gemini(file_path)
            return text, "gemini"
        except Exception as e:
            logger.warning("[Extraction] Tier 1 (Gemini) failed: %s. Trying Tier 2...", e)
            errors.append(f"Tier 1 (Gemini): {e}")
    else:
        logger.warning("[Extraction] Skipping Tier 1 — no INGESTION keys configured")
        errors.append("Tier 1 (Gemini): No API keys configured")

    # Tier 2 — Docling (local, handles tables)
    try:
        text = await _extract_with_docling(file_path)
        return text, "docling"
    except Exception as e:
        logger.warning("[Extraction] Tier 2 (Docling) failed: %s. Trying Tier 3...", e)
        errors.append(f"Tier 2 (Docling): {e}")

    # Tier 3 — PyMuPDF (text-only, last resort)
    try:
        text = await _extract_with_pymupdf(file_path)
        return text, "pymupdf_text_only"
    except Exception as e:
        errors.append(f"Tier 3 (PyMuPDF): {e}")

    # All tiers failed
    raise RuntimeError(
        f"All extraction tiers failed for {file_path}:\n" + "\n".join(errors)
    )


# ══════════════════════════════════════════════════════════════════════
# Core async processing logic
# ══════════════════════════════════════════════════════════════════════

async def _process_file_async(file_id: str) -> None:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    db = get_db()

    # 1. Look up file metadata
    logger.info("[ingestion] Looking up file_id=%s", file_id)
    doc = await db.file_metadata.find_one({"file_id": file_id})
    if not doc:
        logger.error("[ingestion] file_id=%s not found in database", file_id)
        return

    storage_path = doc["storage_path"]
    file_type = doc["file_type"]
    classroom_id = doc.get("classroom_id", "")
    doc_type = doc.get("doc_type", "")
    original_name = doc.get("original_name", "unknown")
    uploaded_by = doc.get("uploaded_by", "")

    # 2. Mark as processing
    await db.file_metadata.update_one(
        {"file_id": file_id},
        {"$set": {"processing.status": "processing", "processing.error": None}},
    )

    try:
        # 3. Extract text (3-tier cascade)
        logger.info("[ingestion] Starting extraction for %s (%s)", original_name, file_type)
        t_start = time.time()
        full_text, extraction_method = await _extract_text_tiered(storage_path, file_type)
        t_extract = time.time() - t_start
        logger.info("[ingestion] Extracted %d chars using %s in %.1fs",
                    len(full_text), extraction_method, t_extract)

        if not full_text.strip():
            raise RuntimeError("Extraction returned empty text")

        # 4. Chunk
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_text(full_text)
        if not chunks:
            raise RuntimeError("Chunking produced zero chunks")

        chunk_records = [
            {
                "id": f"{file_id}_c{idx}",
                "chunk_index": idx,
                "text": text,
            }
            for idx, text in enumerate(chunks, 1)
        ]
        logger.info("[ingestion] Produced %d chunks", len(chunk_records))

        # 5. Embed — use INGESTION key pool with retry backoff
        logger.info("[ingestion] Embedding %d chunks...", len(chunk_records))
        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(chunk_records), EMBED_BATCH_SIZE):
            batch = chunk_records[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_texts = [r["text"] for r in batch]

            for attempt in range(5):
                try:
                    embed_client, embed_key = ingestion_key_manager.get_client()
                    resp = await embed_client.aio.models.embed_content(
                        model=EMBED_MODEL,
                        contents=batch_texts,
                        config={"task_type": "RETRIEVAL_DOCUMENT"},
                    )
                    for emb in resp.embeddings:
                        all_embeddings.append(list(emb.values))
                    break  # Batch success

                except Exception as e:
                    err = str(e)
                    if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt < 4:
                        wait = 2 ** (attempt + 1)
                        logger.warning(
                            "[ingestion] Embedding 429 (batch %d, attempt %d). Waiting %ds...",
                            batch_start // EMBED_BATCH_SIZE, attempt + 1, wait,
                        )
                        ingestion_key_manager.mark_unhealthy(embed_key, duration=wait * 2)
                        await asyncio.sleep(wait)
                        continue
                    raise RuntimeError(f"Embedding failed after {attempt+1} attempts: {e}")

        if len(all_embeddings) != len(chunk_records):
            raise RuntimeError(
                f"Embedding mismatch: got {len(all_embeddings)} embeddings for {len(chunk_records)} chunks"
            )

        # 6. Store in ChromaDB
        logger.info("[ingestion] Storing %d vectors in ChromaDB...", len(chunk_records))
        metadatas = [
            {
                "file_id": file_id,
                "file_name": original_name,
                "file_type": file_type,
                "classroom_id": classroom_id,
                "doc_type": doc_type,
                "uploaded_by": uploaded_by,
                "extraction_method": extraction_method,  # Track which tier was used
            }
            for _ in chunk_records
        ]

        collection = get_chroma_collection()
        collection.upsert(
            ids=[r["id"] for r in chunk_records],
            documents=[r["text"] for r in chunk_records],
            embeddings=all_embeddings,
            metadatas=metadatas,
        )

        # 7. Mark complete in MongoDB
        await db.file_metadata.update_one(
            {"file_id": file_id},
            {
                "$set": {
                    "processing.status": "completed",
                    "processing.chunk_count": len(chunk_records),
                    "processing.extraction_method": extraction_method,
                    "processing.extraction_warning": (
                        "Text extracted without table/image understanding. "
                        "Re-upload may improve quality."
                        if extraction_method == "pymupdf_text_only" else None
                    ),
                    "processing.error": None,
                }
            },
        )
        logger.info("[ingestion] ✓ Completed file_id=%s via %s", file_id, extraction_method)

        # 8. Notify frontend via WebSocket
        await manager.publish_update(classroom_id, {
            "type": "file_processed",
            "file_id": file_id,
            "status": "ready",
            "extraction_method": extraction_method,
            "warning": "pymupdf_text_only" if extraction_method == "pymupdf_text_only" else None,
        })

    except Exception as exc:
        logger.exception("[ingestion] ✗ Failed file_id=%s: %s", file_id, exc)

        await db.file_metadata.update_one(
            {"file_id": file_id},
            {
                "$set": {
                    "processing.status": "failed",
                    "processing.error": str(exc)[:500],
                }
            },
        )

        # Notify frontend of failure
        try:
            await manager.publish_update(classroom_id, {
                "type": "file_processed",
                "file_id": file_id,
                "status": "failed",
                "error": str(exc)[:200],
            })
        except Exception:
            pass

        raise  # Re-raise so Celery can handle retry logic


# ══════════════════════════════════════════════════════════════════════
# Celery Task Entry Point
# ══════════════════════════════════════════════════════════════════════

@celery_app.task(
    name="ingestion.process_file_task",
    # Retry up to 3 times if the task raises any exception
    autoretry_for=(RuntimeError, Exception),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,         # Exponential backoff between retries (1s, 2s, 4s)
    retry_backoff_max=120,      # Cap backoff at 2 minutes
    retry_jitter=True,          # Add jitter to prevent thundering herd
    # Hard limits to prevent runaway tasks
    time_limit=900,             # Hard kill after 15 minutes
    soft_time_limit=840,        # SIGTERM warning at 14 minutes (lets us handle gracefully)
)
def process_file_task(file_id: str):
    """
    Celery entry point. Bridges to the async processing logic.
    Retries up to 3x with exponential backoff on failure.
    """
    async def _run():
        from database.mongo import connect_db, close_db
        from database.chroma import connect_chroma
        await connect_db()
        connect_chroma()
        try:
            await _process_file_async(file_id)
        finally:
            await close_db()

    asyncio.run(_run())
