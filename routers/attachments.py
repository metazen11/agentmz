"""Routers for Task Attachment CRUD operations."""
import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
from fastapi.responses import FileResponse

from database import get_db
from models import Task, TaskAttachment, TaskComment
from routers.tasks import get_task_or_404

router = APIRouter()

class AttachmentResponse(BaseModel):
    id: int
    task_id: int
    comment_id: Optional[int]
    filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    url: str
    uploaded_by: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

def get_uploads_root() -> Path:
    """Resolve uploads directory from env or default under project root."""
    root = os.getenv("UPLOADS_DIR")
    if not root:
        root = str(Path(__file__).parent.parent / "uploads")
    return Path(root).resolve()


def get_attachment_max_bytes() -> int:
    """Return max attachment size in bytes."""
    raw = os.getenv("ATTACHMENT_MAX_BYTES", str(10 * 1024 * 1024))
    try:
        return int(raw)
    except ValueError:
        return 10 * 1024 * 1024


def build_attachment_url(task_id: int, attachment_id: int) -> str:
    return f"/tasks/{task_id}/attachments/{attachment_id}/download"


def resolve_storage_path(storage_path: str) -> Path:
    """Resolve a stored relative path under uploads root."""
    candidate = Path(storage_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(status_code=400, detail="Invalid storage path")
    uploads_root = get_uploads_root()
    full_path = (uploads_root / candidate).resolve()
    if not str(full_path).startswith(str(uploads_root)):
        raise HTTPException(status_code=400, detail="Invalid storage path")
    return full_path

def get_attachment_or_404(task_id: int, attachment_id: int, db: Session) -> TaskAttachment:
    attachment = db.query(TaskAttachment).filter(
        TaskAttachment.id == attachment_id,
        TaskAttachment.task_id == task_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment

@router.get("/tasks/{task_id}/attachments", response_model=List[AttachmentResponse])
def list_task_attachments(
    task_id: int, comment_id: Optional[int] = None, db: Session = Depends(get_db)
):
    get_task_or_404(task_id, db)
    query = db.query(TaskAttachment).filter(TaskAttachment.task_id == task_id)
    if comment_id is not None:
        query = query.filter(TaskAttachment.comment_id == comment_id)
    return query.order_by(TaskAttachment.created_at.asc()).all()


@router.post("/tasks/{task_id}/attachments", response_model=AttachmentResponse)
async def upload_task_attachment(
    task_id: int,
    file: UploadFile = File(...),
    comment_id: Optional[int] = Form(None),
    uploaded_by: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    get_task_or_404(task_id, db)
    if comment_id is not None:
        get_comment_or_404(task_id, comment_id, db)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Attachment is empty")
    max_bytes = get_attachment_max_bytes()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Attachment exceeds size limit")

    safe_name = Path(file.filename or "attachment").name
    safe_name = safe_name or "attachment"
    ext = Path(safe_name).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    relative_dir = Path("tasks") / str(task_id)
    relative_path = (relative_dir / stored_name).as_posix()

    uploads_root = get_uploads_root()
    (uploads_root / relative_dir).mkdir(parents=True, exist_ok=True)
    full_path = resolve_storage_path(relative_path)

    try:
        with full_path.open("wb") as handle:
            handle.write(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write attachment: {exc}") from exc

    mime_type = file.content_type or "application/octet-stream"
    db_attachment = TaskAttachment(
        task_id=task_id,
        comment_id=comment_id,
        filename=safe_name,
        mime_type=mime_type,
        size_bytes=len(content),
        storage_path=relative_path,
        url="pending",
        uploaded_by=(uploaded_by or "").strip() or "human",
    )
    db.add(db_attachment)
    db.flush()
    db_attachment.url = build_attachment_url(task_id, db_attachment.id)
    try:
        db.commit()
    except Exception as exc:
        if full_path.exists():
            full_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save attachment: {exc}") from exc
    db.refresh(db_attachment)
    return db_attachment


@router.get("/tasks/{task_id}/attachments/{attachment_id}/download")
def download_task_attachment(task_id: int, attachment_id: int, db: Session = Depends(get_db)):
    attachment = get_attachment_or_404(task_id, attachment_id, db)
    full_path = resolve_storage_path(attachment.storage_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(
        full_path,
        media_type=attachment.mime_type,
        filename=attachment.filename,
    )


@router.delete("/tasks/{task_id}/attachments/{attachment_id}")
def delete_task_attachment(task_id: int, attachment_id: int, db: Session = Depends(get_db)):
    attachment = get_attachment_or_404(task_id, attachment_id, db)
    full_path = resolve_storage_path(attachment.storage_path)
    if full_path.exists():
        try:
            full_path.unlink()
        except OSError:
            pass
    db.delete(attachment)
    db.commit()
    return {"deleted": True, "attachment_id": attachment_id}
