"""Utility functions for routers."""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import Task

def get_task_or_404(task_id: int, db: Session) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
