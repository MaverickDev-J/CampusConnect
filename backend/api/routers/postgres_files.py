"""Authenticated file routes backed by PostgreSQL and durable ingestion jobs."""
import hashlib
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from api.dependencies import get_current_user
from api.routers.upload import ALL_ALLOWED, MAX_FILE_SIZE, _mime_to_file_type
from core.security import decode_access_token
import jwt
from core.telemetry import operation_trace

router = APIRouter(tags=["Files"])


def public_metadata(document):
    status = "completed" if document["status"] == "ready" else document["status"]
    if status == "failed" and document.get("job_state") == "pending":
        status = "pending"
    return {key: value for key, value in document.items() if key not in {"storage_path", "sha256_hash"}} | {
        "processing": {"status": status,
                       "chunk_count": document.get("chunk_count", 0), "error": document.get("processing_error")},
        "source": {"type": "upload"},
        "academic": {"doc_type": document.get("doc_type") or "academic_material"},
        "playback_url": f"/api/files/{document['file_id']}/download?inline=true",
    }


@router.post("/api/upload/file", status_code=202)
async def upload(request: Request, file: UploadFile = File(...), classroom_id: str = Form(...),
                 doc_type: str | None = Form(None), principal=Depends(get_current_user)):
    async with operation_trace(request.app.state.files.factory,principal,classroom_id,'upload.enqueue',
            kind='ingestion',resource_type='file') as trace:
        result=await _upload(request,file,classroom_id,doc_type,principal)
        trace.resource_id=result['file_id']
        return result


async def _upload(request,file,classroom_id,doc_type,principal):
    await request.app.state.files.authorize(principal, classroom_id, write=True)
    mime = file.content_type or ""
    if mime not in ALL_ALLOWED:
        raise HTTPException(415, "Unsupported file type")
    file_id = "file_" + uuid4().hex
    file_type = _mime_to_file_type(mime)
    extension = {"application/pdf": ".pdf", "image/png": ".png", "image/webp": ".webp",
                 "video/mp4": ".mp4", "video/webm": ".webm"}.get(mime, ".jpg")
    root = request.app.state.storage_root
    path = root / "uploads" / f"{file_id}{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    keep = False
    try:
        async with aiofiles.open(path, "wb") as handle:
            while block := await file.read(8192):
                size += len(block)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(413, "File exceeds 15 MB")
                digest.update(block)
                await handle.write(block)
        if not size:
            raise HTTPException(400, "File is empty")
        # Make bytes durable before a committed queue record can reach a worker.
        if persist := getattr(request.app.state, 'persist_upload', None):
            await persist()
        document = {"file_id": file_id, "classroom_id": classroom_id,
                    "original_name": Path(file.filename or "upload").name, "storage_path": str(path),
                    "file_type": file_type, "sha256_hash": digest.hexdigest(), "uploaded_by": principal["user_id"],
                    "mime_type": mime, "file_size_bytes": size, "doc_type": doc_type}
        saved_id, keep = await request.app.state.files.register(principal, document)
        metadata = await request.app.state.files.get(principal, saved_id)
        return {"file_id": saved_id, "original_name": metadata["original_name"], "file_type": file_type,
                "status": metadata["status"], "message": "Uploaded. Queued for processing." if keep else "File already exists"}
    finally:
        if not keep:
            path.unlink(missing_ok=True)


@router.get("/api/files")
async def files(request: Request, classroom_id: str, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                doc_type: str | None = None, file_type: str | None = None, principal=Depends(get_current_user)):
    rows, total = await request.app.state.files.list(principal, classroom_id, page, limit, doc_type, file_type)
    return {"files": [public_metadata(row) for row in rows], "count": len(rows), "total": total, "page": page}


@router.get("/api/files/{file_id}")
async def file_metadata(file_id: str, request: Request, principal=Depends(get_current_user)):
    return public_metadata(await request.app.state.files.get(principal, file_id))


@router.get("/api/files/{file_id}/download")
async def download(file_id: str, request: Request, token: str | None = None, inline: bool = False):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ") or token
    try:
        user_id = decode_access_token(token or "").get("user_id")
        principal = await request.app.state.accounts.by_id(user_id) if user_id else None
    except (jwt.InvalidTokenError, ValueError, TypeError):
        principal = None
    if not principal:
        raise HTTPException(401, "Authentication required")
    document = await request.app.state.files.get(principal, file_id)
    path = Path(document["storage_path"]).resolve()
    if not path.is_relative_to(request.app.state.storage_root) or not path.is_file():
        raise HTTPException(404, "File content not found")
    return FileResponse(path, filename=document["original_name"], media_type=document["mime_type"],
        content_disposition_type="inline" if inline else "attachment",
        headers={"Referrer-Policy": "no-referrer", "Cache-Control": "private, no-store"})


@router.post("/api/files/{file_id}/retry", status_code=202)
async def retry(file_id: str, request: Request, principal=Depends(get_current_user)):
    await request.app.state.files.retry(principal, file_id)
    return {"message": "Retry triggered", "status": "pending"}


@router.delete('/api/files/{file_id}', status_code=202)
async def remove_file(file_id: str, request: Request, principal=Depends(get_current_user)):
    document=await request.app.state.files.get(principal,file_id)
    async with operation_trace(request.app.state.files.factory,principal,document['classroom_id'],'file.delete',
            kind='cleanup',resource_type='file',resource_id=file_id):
        return await request.app.state.files.delete(principal,file_id)
