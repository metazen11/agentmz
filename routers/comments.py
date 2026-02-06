"""Routers for Task Comment CRUD operations."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Task, TaskComment
from routers.utils import get_task_or_404

router = APIRouter()

class CommentCreate(BaseModel):
    author: Optional[str] = None
    body: str


class CommentUpdate(BaseModel):
    author: Optional[str] = None
    body: Optional[str] = None


class CommentResponse(BaseModel):
    id: int
    task_id: int
    author: str
    body: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


def get_comment_or_404(task_id: int, comment_id: int, db: Session) -> TaskComment:
    comment = (
        db.query(TaskComment)
        .filter(TaskComment.id == comment_id, TaskComment.task_id == task_id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment

@router.get("/tasks/{task_id}/comments", response_model=List[CommentResponse])
def list_task_comments(task_id: int, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    return (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )


@router.post("/tasks/{task_id}/comments", response_model=CommentResponse)
def create_task_comment(task_id: int, comment: CommentCreate, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    author = (comment.author or "").strip() or "human"
    db_comment = TaskComment(task_id=task_id, author=author, body=comment.body)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


@router.patch("/tasks/{task_id}/comments/{comment_id}", response_model=CommentResponse)
def update_task_comment(
    task_id: int, comment_id: int, update: CommentUpdate, db: Session = Depends(get_db)
):
    comment = get_comment_or_404(task_id, comment_id, db)
    if update.body is None and update.author is None:
        raise HTTPException(status_code=400, detail="No updates provided")
    if update.body is not None:
        comment.body = update.body
    if update.author is not None:
        comment.author = (update.author or "").strip() or "human"
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/tasks/{task_id}/comments/{comment_id}")
def delete_task_comment(task_id: int, comment_id: int, db: Session = Depends(get_db)):
    comment = get_comment_or_404(task_id, comment_id, db)
    db.delete(comment)
    db.commit()
    return {"deleted": True, "comment_id": comment_id}
