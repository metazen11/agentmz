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
    import json

    if not payload.request.strip():
        raise HTTPException(status_code=400, detail="Request is required")
    task = get_task_or_404(task_id, db)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    context = build_task_context_summary(task, project, db)

    node = context.get("node") or {}
    node_prompt = node.get("agent_prompt")
    project_info = context.get("project") or {}
    objective = context.get("objective")
    last_comment = context.get("last_comment") or {}
    recent_files = context.get("recent_files") or {}
    discovery = context.get("discovery") or {}
    mcp_info = context.get("mcp") or {}

    system_info = os.getenv("APP_URL") or "https://wfhub.localhost"
    main_api = os.getenv("MAIN_API_URL") or "http://localhost:8002"
    request_body = payload.request.strip() or "Execute the task using the provided context."

    image_context = None
    if payload.image_context:
        raw_context = payload.image_context.strip()
        if raw_context.startswith("IMAGE_CONTEXT"):
            _, _, json_blob = raw_context.partition("\n")
            try:
                image_context = json.loads(json_blob)
            except json.JSONDecodeError:
                image_context = raw_context
        else:
            image_context = raw_context

    if not discovery.get("endpoints"):
        discovery = {
            "instructions": (
                "Fetch more context only if needed for the objective. "
                "Use the endpoints below to query additional details."
            ),
            "endpoints": {
                "task": f"/tasks/{task.id}",
                "comments": f"/tasks/{task.id}/comments",
                "attachments": f"/tasks/{task.id}/attachments",
                "acceptance": f"/tasks/{task.id}/acceptance",
                "runs": f"/tasks/{task.id}/runs",
                "project_files": f"/projects/{project.id}/files",
                "git_status": f"/projects/{project.id}/git/status",
                "help": "/help/agents",
            },
        }

    endpoint_guidance = {
        "task": {
            "method": "GET",
            "description": "Fetch the full task record, including title, description, status, and metadata."
        },
        "comments": {
            "method": "GET/POST",
            "description": "GET comments for context and POST `{body, author}` to create a new note."
        },
        "attachments": {
            "method": "GET/POST",
            "description": "GET attachment list or POST multipart/form-data with a file field to upload proof."
        },
        "acceptance": {
            "method": "GET",
            "description": "Read acceptance criteria; mark items as passed via PATCH if available."
        },
        "runs": {
            "method": "GET/POST",
            "description": "GET run history or POST `{node_id, status, summary}` to record a new run."
        },
        "project_files": {
            "method": "GET",
            "description": "List workspace files to locate code referenced by the task."
        },
        "git_status": {
            "method": "GET",
            "description": "Inspect git status to know what is staged, modified, or untracked."
        },
        "help": {
            "method": "GET",
            "description": "Call `/help/agents` for expert guidance on using the API."
        },
    }
    described_endpoints = []
    raw_endpoints = mcp_info.get("endpoints") or {}
    for name, path in raw_endpoints.items():
        guidance = endpoint_guidance.get(name, {})
        produced_path = path
        if not produced_path.startswith("http"):
            produced_path = main_api.rstrip("/") + (path.startswith("/") ? "" : "/") + path
        described_endpoints.append({
            "name": name,
            "path": produced_path,
            "method": guidance.get("method", "GET"),
            "description": guidance.get("description", "Call this endpoint for more context."),
        })
    help_url = main_api.rstrip("/") + "/help/agents"

    prompt_payload = {
        "project": {
            "name": project_info.get("name"),
            "workspace_path": project_info.get("workspace_path"),
            "environment": project_info.get("environment"),
        } if project_info else None,
        "system_domain": system_info,
        "objective": objective,
        "last_comment": {
            "author": last_comment.get("author"),
            "body": last_comment.get("body"),
        } if last_comment.get("body") else None,
        "recent_files": {
            "last_commit_summary": recent_files.get("last_commit_summary"),
            "last_commit_files": recent_files.get("last_commit_files"),
            "working_changes": recent_files.get("working_changes"),
        },
        "mcp": {
            "notes": mcp_info.get("notes"),
            "endpoints": described_endpoints,
            "reporting": mcp_info.get("reporting"),
            "help": help_url,
        } if mcp_info else None,
        "discovery": discovery,
        "acceptance_criteria": [
            item.get("description")
            for item in (context.get("acceptance_criteria") or [])
            if item.get("description")
        ],
        "image_context": image_context,
        "request": request_body,
    }

    def _compact(value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                compacted = _compact(item)
                if compacted is None:
                    continue
                if compacted == "" or compacted == [] or compacted == {}:
                    continue
                cleaned[key] = compacted
            return cleaned
        if isinstance(value, list):
            cleaned_list = []
            for item in value:
                compacted = _compact(item)
                if compacted is None:
                    continue
                if compacted == "" or compacted == [] or compacted == {}:
                    continue
                cleaned_list.append(compacted)
            return cleaned_list
        return value

    compact_payload = _compact(prompt_payload)
    prompt = json.dumps(compact_payload, indent=2)
    if request_body:
        prompt = f"{prompt}\n\nREQUEST:\n{request_body}"
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
