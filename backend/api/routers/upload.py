"""Upload router – multi-modal file upload with streaming SHA-256 dedup."""

import hashlib
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from api.dependencies import get_current_user, require_classroom_member
from database.mongo import get_db

router = APIRouter(prefix="/api/upload", tags=["Upload"])
files_router = APIRouter(prefix="/api/files", tags=["Files"])
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

STORAGE_BASE = Path("storage")
TEMP_DIR = STORAGE_BASE / "temp"
UPLOAD_DIR = STORAGE_BASE / "uploads"

PDF_MIMES = ["application/pdf"]
IMAGE_MIMES = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
VIDEO_MIMES = ["video/mp4", "video/webm"]

ALL_ALLOWED = PDF_MIMES + IMAGE_MIMES + VIDEO_MIMES
STUDENT_ALLOWED = PDF_MIMES + IMAGE_MIMES

CHUNK_SIZE = 8192
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB hard limit

_STATIC_DIRS = {"pdf": "pdfs", "image": "images", "video": "videos"}


def _mime_to_file_type(mime: str) -> str:
    if mime in PDF_MIMES:
        return "pdf"
    if mime in IMAGE_MIMES:
        return "image"
    if mime in VIDEO_MIMES:
        return "video"
    return "unknown"


def _build_playback_url(file_doc: dict) -> str:
    ft = file_doc.get("file_type", "pdf")
    folder = _STATIC_DIRS.get(ft, "pdfs")
    original = file_doc.get("original_name", "file.bin")
    ext = Path(original).suffix or ".bin"
    return f"/static/{folder}/{file_doc['file_id']}{ext}"


# ── POST /api/upload/file ────────────────────────────────────────────

@router.post("/file", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    classroom_id: str = Form(..., min_length=1),
    doc_type: str = Form(None),
    current_user: dict = Depends(get_current_user),
):
    role = current_user.get("role")
    mime = file.content_type or ""

    # ① Permission gate — only teachers and superadmins can upload
    if role not in ("teacher", "superadmin"):
        raise HTTPException(status_code=403, detail="Only teachers can upload files")

    if mime not in ALL_ALLOWED:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    # ② Validate classroom membership
    db = get_db()
    classroom = await db.classrooms.find_one({"classroom_id": classroom_id})
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    member_ids = [m["user_id"] for m in classroom.get("members", [])]
    if role != "superadmin" and current_user["user_id"] not in member_ids:
        raise HTTPException(status_code=403, detail="You must be a member of this classroom to upload")

    # ③ Determine file type + extension
    file_type = _mime_to_file_type(mime)
    ext = Path(file.filename or "file").suffix or ".bin"

    # ④ SHA-256 streaming hash + save to temp
    temp_name = f"{uuid4().hex}{ext}"
    temp_path = TEMP_DIR / temp_name
    hasher = hashlib.sha256()
    file_size = 0

    try:
        async with aiofiles.open(temp_path, "wb") as tmp:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                await tmp.write(chunk)
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum is {MAX_FILE_SIZE // (1024*1024)} MB.",
                    )
    except HTTPException:
        # Clean up partial temp file then re-raise
        if temp_path.exists():
            temp_path.unlink()
        raise

    sha256_hash = hasher.hexdigest()

    # ⑤ Dedup check
    existing = await db.file_metadata.find_one({"sha256_hash": sha256_hash})
    if existing:
        temp_path.unlink(missing_ok=True)
        status_str = existing.get("processing", {}).get("status", "unknown")

        # Re-trigger ingestion if previously failed
        if status_str == "failed":
            logger.info("[upload] Re-triggering failed ingestion for: %s", existing["file_id"])
            from api.services.ingestion import process_file_task
            await db.file_metadata.update_one(
                {"file_id": existing["file_id"]},
                {"$set": {"processing.status": "pending", "processing.error": None}},
            )
            process_file_task.delay(existing["file_id"])
            return {
                "file_id": existing["file_id"],
                "message": "File already exists but ingestion had failed. Re-triggering now.",
                "status": "pending",
            }

        return {
            "file_id": existing["file_id"],
            "message": "File already exists",
            "status": status_str,
        }

    # ⑥ Move to permanent storage
    file_id = f"file_{uuid4().hex}"
    permanent_dir = UPLOAD_DIR / f"{file_type}s"
    permanent_dir.mkdir(parents=True, exist_ok=True)
    permanent_path = permanent_dir / f"{file_id}{ext}"

    try:
        shutil.move(str(temp_path), str(permanent_path))
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # ⑦ Save metadata to MongoDB (using timezone-aware datetime)
    now = datetime.now(timezone.utc)
    doc = {
        "file_id": file_id,
        "original_name": file.filename,
        "storage_path": str(permanent_path),
        "mime_type": mime,
        "file_type": file_type,
        "file_size_bytes": file_size,
        "sha256_hash": sha256_hash,
        "source": {"type": "upload", "youtube_video_id": None},
        "classroom_id": classroom_id,
        "doc_type": doc_type,
        "processing": {
            "status": "pending",
            "chunk_count": 0,
            "page_count": None,
            "error": None,
        },
        "uploaded_by": current_user["user_id"],
        "uploaded_at": now,  # ← timezone-aware (was naive datetime.utcnow())
    }

    try:
        await db.file_metadata.insert_one(doc)
    except Exception as e:
        # Rollback: remove the physical file if metadata write fails
        if permanent_path.exists():
            permanent_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save file metadata: {e}")

    # ⑧ Trigger background ingestion
    from api.services.ingestion import process_file_task
    process_file_task.delay(file_id)

    return {
        "file_id": file_id,
        "original_name": file.filename,
        "file_type": file_type,
        "status": "pending",
        "message": "Uploaded. Processing in background.",
    }


# ── GET /api/files ───────────────────────────────────────────────────

@files_router.get("")
async def list_files(
    classroom_id: str = Query(..., description="Classroom ID"),
    doc_type: str | None = Query(None),
    file_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """List classroom-scoped files. Paginated."""
    db = get_db()

    if current_user["role"] != "superadmin":
        await require_classroom_member(classroom_id, current_user["user_id"])

    query: dict = {"classroom_id": classroom_id}
    if doc_type:
        query["doc_type"] = doc_type
    if file_type:
        query["file_type"] = file_type

    skip = (page - 1) * limit
    total = await db.file_metadata.count_documents(query)
    cursor = (
        db.file_metadata.find(query, {"storage_path": 0, "sha256_hash": 0, "_id": 0})
        .sort("uploaded_at", -1)
        .skip(skip)
        .limit(limit)
    )
    files = await cursor.to_list(length=limit)

    for f in files:
        f["playback_url"] = _build_playback_url(f)
        if isinstance(f.get("uploaded_at"), datetime):
            f["uploaded_at"] = f["uploaded_at"].isoformat()
        source = f.get("source", {})
        if source.get("type") == "youtube":
            f["youtube_video_id"] = source.get("youtube_video_id")

    return {"files": files, "count": len(files), "total": total, "page": page}


# ── GET /api/files/{file_id} ─────────────────────────────────────────

@files_router.get("/{file_id}")
async def get_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return metadata for a single file by file_id."""
    db = get_db()

    doc = await db.file_metadata.find_one(
        {"file_id": file_id},
        {"storage_path": 0, "sha256_hash": 0, "_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    if current_user["role"] != "superadmin":
        await require_classroom_member(doc.get("classroom_id", ""), current_user["user_id"])

    doc["playback_url"] = _build_playback_url(doc)
    if isinstance(doc.get("uploaded_at"), datetime):
        doc["uploaded_at"] = doc["uploaded_at"].isoformat()

    source = doc.get("source", {})
    if source.get("type") == "youtube":
        doc["youtube_video_id"] = source.get("youtube_video_id")

    return doc


# ── GET /api/files/{file_id}/download ───────────────────────────────

@files_router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    token: str | None = Query(None, description="Bearer token (for use in <a> href links)"),
    current_user: dict = Depends(get_current_user),
):
    """
    Download a file with its original filename.
    Supports both Authorization header (standard) and ?token= query param
    (for use in direct download links in <a> tags).
    
    Note: ?token= support is provided by the Depends(get_current_user) 
    which reads from the Authorization header. For query-param token support,
    the frontend should set the Authorization header instead.
    """
    db = get_db()

    doc = await db.file_metadata.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    if current_user["role"] != "superadmin":
        await require_classroom_member(doc.get("classroom_id", ""), current_user["user_id"])

    file_path = Path(doc["storage_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File content not found on server")

    return FileResponse(
        path=file_path,
        filename=doc["original_name"],
        media_type=doc["mime_type"],
    )


# ── POST /api/files/{file_id}/retry ─────────────────────────────────

@files_router.post("/{file_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_file_ingestion(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Manually retry ingestion for a failed file."""
    if current_user["role"] not in ("teacher", "superadmin"):
        raise HTTPException(status_code=403, detail="Only teachers can retry ingestion")

    db = get_db()
    doc = await db.file_metadata.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    await db.file_metadata.update_one(
        {"file_id": file_id},
        {"$set": {"processing.status": "pending", "processing.error": None}},
    )

    from api.services.ingestion import process_file_task
    process_file_task.delay(file_id)

    return {"message": "Retry triggered", "status": "pending"}
