"""Routers for Task Acceptance Criteria CRUD operations."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Task, TaskAcceptanceCriteria
from routers.utils import get_task_or_404

router = APIRouter()

class AcceptanceCriteriaCreate(BaseModel):
    description: str
    passed: Optional[bool] = None
    author: Optional[str] = None


class AcceptanceCriteriaUpdate(BaseModel):
    description: Optional[str] = None
    passed: Optional[bool] = None
    author: Optional[str] = None


class AcceptanceCriteriaResponse(BaseModel):
    id: int
    task_id: int
    description: str
    passed: bool
    author: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


def get_acceptance_or_404(task_id: int, criteria_id: int, db: Session) -> TaskAcceptanceCriteria:
    criteria = (
        db.query(TaskAcceptanceCriteria)
        .filter(
            TaskAcceptanceCriteria.id == criteria_id,
            TaskAcceptanceCriteria.task_id == task_id,
        )
        .first()
    )
    if not criteria:
        raise HTTPException(status_code=404, detail="Acceptance criteria not found")
    return criteria


@router.get("/tasks/{task_id}/acceptance", response_model=List[AcceptanceCriteriaResponse])
def list_task_acceptance(task_id: int, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    return (
        db.query(TaskAcceptanceCriteria)
        .filter(TaskAcceptanceCriteria.task_id == task_id)
        .order_by(TaskAcceptanceCriteria.created_at.asc())
        .all()
    )


@router.post("/tasks/{task_id}/acceptance", response_model=AcceptanceCriteriaResponse)
def create_task_acceptance(
    task_id: int, criteria: AcceptanceCriteriaCreate, db: Session = Depends(get_db)
):
    get_task_or_404(task_id, db)
    author = (criteria.author or "").strip() or "user"
    passed = bool(criteria.passed) if criteria.passed is not None else False
    db_criteria = TaskAcceptanceCriteria(
        task_id=task_id,
        description=criteria.description,
        passed=passed,
        author=author,
    )
    db.add(db_criteria)
    db.commit()
    db.refresh(db_criteria)
    return db_criteria


@router.patch("/tasks/{task_id}/acceptance/{criteria_id}", response_model=AcceptanceCriteriaResponse)
def update_task_acceptance(
    task_id: int,
    criteria_id: int,
    update: AcceptanceCriteriaUpdate,
    db: Session = Depends(get_db),
):
    criteria = get_acceptance_or_404(task_id, criteria_id, db)
    if update.description is None and update.passed is None and update.author is None:
        raise HTTPException(status_code=400, detail="No updates provided")
    if update.description is not None:
        criteria.description = update.description
    if update.passed is not None:
        criteria.passed = update.passed
    if update.author is not None:
        criteria.author = (update.author or "").strip() or "user"
    db.commit()
    db.refresh(criteria)
    return criteria


@router.delete("/tasks/{task_id}/acceptance/{criteria_id}")
def delete_task_acceptance(task_id: int, criteria_id: int, db: Session = Depends(get_db)):
    criteria = get_acceptance_or_404(task_id, criteria_id, db)
    db.delete(criteria)
    db.commit()
    return {"deleted": True, "criteria_id": criteria_id}
