"""Routers for Task CRUD operations."""
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Project, Task, TaskAcceptanceCriteria, TaskNode, TaskExternalLink
from core.context import build_task_context_payload, build_task_context_summary
from routers.nodes import get_node_or_404, get_default_node
from routers.acceptance_criteria import AcceptanceCriteriaCreate
from routers.acceptance_criteria import AcceptanceCriteriaCreate


class TaskCreate(BaseModel):
    project_id: int
    parent_id: Optional[int] = None
    node_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    acceptance_criteria: Optional[List[AcceptanceCriteriaCreate]] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    node_id: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    parent_id: Optional[int]
    node_id: int
    node_name: Optional[str] = None
    title: str
    description: Optional[str]
    status: str
    created_at: Optional[datetime]
    children: List["TaskResponse"] = []

    class Config:
        from_attributes = True


TaskResponse.model_rebuild()

class TaskPromptRequest(BaseModel):
    request: str
    image_context: Optional[str] = None
    concise: bool = False

class TaskExportRequest(BaseModel):
    integration_id: int

class TaskExternalLinkResponse(BaseModel):
    id: int
    task_id: int
    integration_id: int
    external_task_id: str
    external_url: Optional[str]
    sync_status: str
    sync_hash: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


from routers.utils import get_task_or_404

router = APIRouter()


@router.get("/projects/{project_id}/tasks", response_model=List[TaskResponse])
def list_project_tasks(project_id: int, db: Session = Depends(get_db)):
    """Get task tree for a project (only top-level tasks, children nested)."""
    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.parent_id.is_(None)
    ).all()

    def build_tree(task):
        result = task.to_dict(include_children=False)
        result["children"] = [build_tree(child) for child in task.children]
        return result

    return [build_tree(t) for t in tasks]


@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    # Verify project exists
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify parent task exists if specified
    if task.parent_id:
        parent = db.query(Task).filter(Task.id == task.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent task not found")
        if parent.project_id != task.project_id:
            raise HTTPException(status_code=400, detail="Parent task belongs to a different project")

    criteria_list = task.acceptance_criteria or []
    if not criteria_list:
        raise HTTPException(status_code=400, detail="At least one acceptance criteria is required")

    if task.node_id is not None:
        node = get_node_or_404(task.node_id, db)
    else:
        node = get_default_node(db)

    db_task = Task(
        project_id=task.project_id,
        parent_id=task.parent_id,
        node_id=node.id,
        title=task.title,
        description=task.description,
        status=task.status or "backlog",
    )
    db.add(db_task)
    db.flush()

    for item in criteria_list:
        author = (item.author or "").strip() or "user"
        passed = bool(item.passed) if item.passed is not None else False
        db.add(TaskAcceptanceCriteria(
            task_id=db_task.id,
            description=item.description,
            passed=passed,
            author=author,
        ))

    db.commit()
    db.refresh(db_task)
    return db_task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    task = get_task_or_404(task_id, db)

    if update.title is not None:
        task.title = update.title
    if update.description is not None:
        task.description = update.description
    if update.status is not None:
        task.status = update.status
    if update.node_id is not None:
        node = get_node_or_404(update.node_id, db)
        task.node_id = node.id

    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = get_task_or_404(task_id, db)

    db.delete(task)
    db.commit()
    return {"deleted": True, "task_id": task_id}


@router.post("/tasks/{task_id}/prompt")
def build_task_prompt(task_id: int, payload: TaskPromptRequest, db: Session = Depends(get_db)):
    from typing import List
    import json

    if not payload.request.strip():
        raise HTTPException(status_code=400, detail="Request is required")
    task = get_task_or_404(task_id, db)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    context = (
        build_task_context_summary(task, project, db)
        if payload.concise
        else build_task_context_payload(task, project, db)
    )
    sections: List[str] = []
    node = context.get("node", {})
    node_prompt = node.get("agent_prompt")
    if node_prompt:
        sections.append(f"NODE_DIRECTIVE:\n{node_prompt}\n")

    project_info = context.get("project", {})
    if project_info:
        env_value = project_info.get("environment")
        env_lines = []
        if isinstance(env_value, dict):
            env_lines = [f"{key}={value}" for key, value in env_value.items()]
        elif env_value:
            env_lines = [str(env_value)]
        project_lines = [
            "PROJECT_INFO:",
            f"Name: {project_info.get('name')}",
            f"Workspace: {project_info.get('workspace_path')}",
        ]
        if env_lines:
            project_lines.append("Environment:")
            project_lines.extend(env_lines)
        else:
            project_lines.append("Environment: (not provided)")
        sections.append("\n".join(project_lines) + "\n")
        system_info = os.getenv("APP_URL") or "https://wfhub.localhost"
        sections.append(f"SYSTEM_DOMAIN:\n{system_info}\n")

    objective = context.get("objective")
    if objective:
        sections.append(f"TASK_OBJECTIVE:\n{objective}\n")

    last_comment = context.get("last_comment")
    if last_comment and last_comment.get("body"):
        comment_author = last_comment.get("author", "unknown")
        sections.append(
            f"LAST_COMMENT:\n"
            f"[{comment_author}] {last_comment.get('body')}\n"
        )

    recent_files = context.get("recent_files", {})
    file_lines = []
    if recent_files.get("last_commit_summary"):
        file_lines.append(f"Last commit summary: {recent_files['last_commit_summary']}")
    if recent_files.get("last_commit_files"):
        files_list = ", ".join(recent_files["last_commit_files"])
        file_lines.append(f"Last commit files: {files_list}")
    if recent_files.get("working_changes"):
        working_list = ", ".join(
            f"{item.get('status')} {item.get('path')}"
            for item in recent_files["working_changes"]
            if item.get("path")
        )
        if working_list:
            file_lines.append(f"Working changes: {working_list}")
    if file_lines:
        sections.append(f"RECENT_FILES:\n" + "\n".join(file_lines) + "\n")

    discovery = context.get("discovery", {})
    discovery_lines = []
    if discovery.get("instructions"):
        discovery_lines.append(discovery["instructions"])
    endpoints = discovery.get("endpoints", {})
    if endpoints:
        discovery_lines.append(
            "Endpoints:\n" + "\n".join(f"{key}: {value}" for key, value in endpoints.items())
        )
    if discovery_lines:
        sections.append(f"DISCOVERY:\n" + "\n".join(discovery_lines) + "\n")

    if payload.image_context:
        sections.append(f"IMAGE_CONTEXT:\n{payload.image_context}\n")

    acceptance = context.get("acceptance_criteria") or []
    acceptance_body = "\n".join(
        f"- {item.get('description')}" for item in acceptance if item.get("description")
    )
    if acceptance_body:
        sections.append(f"ACCEPTANCE_CRITERIA:\n{acceptance_body}\n")

    request_body = payload.request.strip() or "Execute the task using the provided context."
    sections.append(f"REQUEST:\n{request_body}\n")

    prompt = "\n".join(section.rstrip() for section in sections if section)
    return {"prompt": prompt}


@router.get("/tasks/{task_id}/context")
def get_task_context(task_id: int, db: Session = Depends(get_db)):
    task = get_task_or_404(task_id, db)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return build_task_context_payload(task, project, db)

@router.post("/tasks/{task_id}/trigger")
def trigger_task(task_id: int, db: Session = Depends(get_db)):
    """Manually trigger the Aider agent for a task."""
    from pathlib import Path
    from agent.aider_runner import run_agent
    from models import TaskRun
    from datetime import datetime

    task = get_task_or_404(task_id, db)

    # Get project for workspace path
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Extract workspace name from path
    workspace_name = Path(project.workspace_path).name

    # Update status to in_progress
    task.status = "in_progress"
    db.commit()

    # Run Aider agent
    run = None
    try:
        run = TaskRun(task_id=task.id, node_id=task.node_id, status="started")
        db.add(run)
        db.commit()
        db.refresh(run)

        result = run_agent(
            workspace_name=workspace_name,
            task_title=task.title,
            task_description=task.description or "",
            task_id=task.id,
            node_name=task.node_name or "dev",
        )

        # Update task status based on result
        if result.get("status") == "PASS":
            task.status = "done"
            run.status = "completed"
        else:
            task.status = "failed"
            run.status = "failed"
            run.error = result.get("summary")
        run.summary = result.get("summary")
        run.finished_at = datetime.utcnow()
        db.commit()

        return {"triggered": True, "task_id": task_id, "run_id": run.id, "result": result}

    except Exception as e:
        task.status = "failed"
        db.commit()
        if run is not None:
            try:
                run.status = "failed"
                run.error = str(e)
                run.finished_at = datetime.utcnow()
                db.commit()
            except Exception:
                db.rollback()
        return {"triggered": False, "task_id": task_id, "error": str(e)}


@router.get("/tasks/{task_id}/external-links", response_model=List[TaskExternalLinkResponse])
def list_task_external_links(task_id: int, db: Session = Depends(get_db)):
    """List external links for a task."""
    get_task_or_404(task_id, db)
    return (
        db.query(TaskExternalLink)
        .filter(TaskExternalLink.task_id == task_id)
        .all()
    )
