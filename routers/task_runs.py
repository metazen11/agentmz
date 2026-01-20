"""Routers for Task Run CRUD operations."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Task, TaskRun
from routers.tasks import get_task_or_404
from routers.nodes import get_node_or_404

router = APIRouter()

class TaskRunCreate(BaseModel):
    node_id: Optional[int] = None


class TaskRunUpdate(BaseModel):
    status: Optional[str] = None
    summary: Optional[str] = None
    tests_run: Optional[list] = None
    screenshots: Optional[list] = None
    tool_calls: Optional[list] = None
    error: Optional[str] = None
    finished_at: Optional[datetime] = None


class TaskRunResponse(BaseModel):
    id: int
    task_id: int
    node_id: int
    status: str
    summary: Optional[str]
    tests_run: Optional[list]
    screenshots: Optional[list]
    tool_calls: Optional[list]
    error: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True

@router.get("/tasks/{task_id}/runs", response_model=List[TaskRunResponse])
def list_task_runs(task_id: int, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    return (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id)
        .order_by(TaskRun.started_at.desc())
        .all()
    )


@router.get("/tasks/{task_id}/runs/{run_id}", response_model=TaskRunResponse)
def get_task_run(task_id: int, run_id: int, db: Session = Depends(get_db)):
    run = (
        db.query(TaskRun)
        .filter(TaskRun.id == run_id, TaskRun.task_id == task_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/tasks/{task_id}/runs", response_model=TaskRunResponse)
def create_task_run(task_id: int, payload: TaskRunCreate, db: Session = Depends(get_db)):
    task = get_task_or_404(task_id, db)
    node_id = payload.node_id or task.node_id
    get_node_or_404(node_id, db)
    run = TaskRun(task_id=task_id, node_id=node_id, status="started")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.patch("/tasks/{task_id}/runs/{run_id}", response_model=TaskRunResponse)
def update_task_run(
    task_id: int,
    run_id: int,
    payload: TaskRunUpdate,
    db: Session = Depends(get_db),
):
    run = (
        db.query(TaskRun)
        .filter(TaskRun.id == run_id, TaskRun.task_id == task_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if (
        payload.status is None
        and payload.summary is None
        and payload.tests_run is None
        and payload.screenshots is None
        and payload.tool_calls is None
        and payload.error is None
        and payload.finished_at is None
    ):
        raise HTTPException(status_code=400, detail="No updates provided")

    if payload.status is not None:
        run.status = payload.status
    if payload.summary is not None:
        run.summary = payload.summary
    if payload.tests_run is not None:
        run.tests_run = payload.tests_run
    if payload.screenshots is not None:
        run.screenshots = payload.screenshots
    if payload.tool_calls is not None:
        run.tool_calls = payload.tool_calls
    if payload.error is not None:
        run.error = payload.error
    if payload.finished_at is not None:
        run.finished_at = payload.finished_at

    db.commit()
    db.refresh(run)
    return run
