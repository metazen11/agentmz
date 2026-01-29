"""Routers for Task CRUD operations."""
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Project, Task, TaskAcceptanceCriteria, TaskNode, TaskExternalLink, TaskRun
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


class SubtaskCreate(BaseModel):
    """Schema for creating a subtask via agent delegation."""
    title: str
    description: Optional[str] = None
    node_id: Optional[int] = None


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
    depth: int = 0
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

    default_discovery_endpoints = {
        "task": f"/tasks/{task.id}",
        "comments": f"/tasks/{task.id}/comments",
        "attachments": f"/tasks/{task.id}/attachments",
        "acceptance": f"/tasks/{task.id}/acceptance",
        "runs": f"/tasks/{task.id}/runs",
        "project_files": f"/projects/{project.id}/files",
        "git_status": f"/projects/{project.id}/git/status",
        "help": "/help/agents",
    }

    endpoint_guidance = {
        "task": {
            "method": "GET",
            "description": "Fetch the full task record, including title, description, status, and metadata.",
            "payload": None,
        },
        "comments": {
            "method": "GET/POST",
            "description": "GET comments for context and POST `{body, author}` to create a new note.",
            "payload": {"body": "text", "author": "agent.<node>"},
        },
        "attachments": {
            "method": "GET/POST",
            "description": "GET attachment list or POST multipart/form-data with a file field to upload proof.",
            "payload": "multipart/form-data with field `file` plus optional metadata",
        },
        "acceptance": {
            "method": "GET/PATCH",
            "description": "GET acceptance criteria; PATCH `{id, passed}` if you mark items as done.",
            "payload": {"id": "number", "passed": "true|false"},
        },
        "runs": {
            "method": "GET/POST",
            "description": "GET run history or POST `{node_id, status, summary}` to record a new run.",
            "payload": {"node_id": task.node_id, "status": "pass|fail", "summary": "text"},
        },
        "project_files": {
            "method": "GET",
            "description": "List workspace files to locate code referenced by the task.",
            "payload": None,
        },
        "git_status": {
            "method": "GET",
            "description": "Inspect git status to know what is staged, modified, or untracked.",
            "payload": None,
        },
        "help": {
            "method": "GET",
            "description": "Call `/help/agents` for expert guidance on using the API.",
            "payload": None,
        },
    }

    discovery_endpoints = discovery.get("endpoints") or {}
    merged_endpoints = {**default_discovery_endpoints, **discovery_endpoints}
    described_endpoints = []
    for name, path in merged_endpoints.items():
        guidance = endpoint_guidance.get(name, {})
        produced_path = path
        if not produced_path.startswith("http"):
            path_prefix = "" if path.startswith("/") else "/"
            produced_path = main_api.rstrip("/") + path_prefix + path
        described_endpoints.append({
            "name": name,
            "url": produced_path,
            "method": guidance.get("method", "GET"),
            "description": guidance.get("description", "Call this endpoint for more context."),
            "payload": guidance.get("payload"),
        })
    help_url = main_api.rstrip("/") + "/help/agents"

    recent_files_payload = {
        "last_commit_summary": recent_files.get("last_commit_summary")
    }
    if not payload.concise:
        recent_files_payload.update({
            "last_commit_files": recent_files.get("last_commit_files"),
            "working_changes": recent_files.get("working_changes"),
        })

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
        "recent_files": recent_files_payload,
        "mcp": {
            "notes": mcp_info.get("notes"),
            "main_api": main_api,
            "system_domain": system_info,
            "endpoints": described_endpoints,
            "reporting": mcp_info.get("reporting"),
            "help": help_url,
        },
        "discovery": {
            "instructions": discovery.get("instructions") or (
                "Fetch more context only if needed for the objective. "
                "Use the endpoints below to query additional details."
            ),
            "endpoints": described_endpoints,
        },
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
async def trigger_task(task_id: int, db: Session = Depends(get_db)):
    """Manually trigger the agent for a task using the agent loop."""
    import httpx
    from pathlib import Path

    AIDER_API_URL = os.getenv("AIDER_API_URL", "http://wfhub-v2-aider-api:8001")

    task = get_task_or_404(task_id, db)

    # Get project for workspace path
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Handle [%root%] variable - pass through directly
    workspace_path = project.workspace_path
    if workspace_path.startswith("[%root%]"):
        workspace_name = workspace_path
    else:
        workspace_name = Path(workspace_path).name

    # Get node for context
    node = db.query(TaskNode).filter(TaskNode.id == task.node_id).first()
    node_name = node.name if node else "dev"
    node_prompt = node.agent_prompt if node else None

    # Build task prompt
    prompt_parts = []
    if node_prompt:
        prompt_parts.append(f"ROLE: {node_prompt}")
    prompt_parts.append(f"TASK: {task.title}")
    if task.description:
        prompt_parts.append(f"\nDESCRIPTION:\n{task.description}")
    prompt_parts.append("\n\nComplete this task. Use the available tools (grep, glob, read, write, edit, bash) as needed.")

    full_prompt = "\n".join(prompt_parts)

    # Update status to in_progress
    task.status = "in_progress"
    db.commit()

    # Create task run record
    run = TaskRun(task_id=task.id, node_id=task.node_id, status="started")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        # Call the agent loop endpoint (not aider CLI)
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{AIDER_API_URL}/api/agent/run",
                json={
                    "task": full_prompt,
                    "workspace": workspace_name,
                    "project_id": project.id,
                    "task_id": task.id,
                    "max_iterations": 20,
                }
            )
            result = response.json()

        # Determine success
        success = result.get("success") or result.get("status") == "PASS"

        # Update task and run status
        if success:
            task.status = "done"
            run.status = "completed"
        else:
            task.status = "failed"
            run.status = "failed"
            run.error = result.get("error") or result.get("summary")

        run.summary = result.get("summary")
        run.tool_calls = result.get("tool_calls")
        run.finished_at = datetime.utcnow()
        db.commit()

        return {"triggered": True, "task_id": task_id, "run_id": run.id, "result": result}

    except httpx.TimeoutException:
        task.status = "failed"
        run.status = "failed"
        run.error = "Agent timeout (>5 minutes)"
        run.finished_at = datetime.utcnow()
        db.commit()
        return {"triggered": False, "task_id": task_id, "error": "Agent timeout"}

    except Exception as e:
        task.status = "failed"
        run.status = "failed"
        run.error = str(e)
        run.finished_at = datetime.utcnow()
        db.commit()
        return {"triggered": False, "task_id": task_id, "error": str(e)}


@router.post("/tasks/{task_id}/subtasks", response_model=TaskResponse)
async def create_subtask(
    task_id: int,
    subtask: SubtaskCreate,
    trigger: bool = True,
    db: Session = Depends(get_db),
):
    """Create a subtask via agent delegation.

    This endpoint is called by agents to delegate work to child agents.
    It enforces:
    - Maximum delegation depth (3 levels)
    - Maximum subtasks per parent (10)
    - Creates TaskRun for audit trail
    - Optionally triggers background execution (trigger=True by default)

    Query Parameters:
        trigger: If True (default), immediately start agent execution in background.
                 If False, just create the subtask without triggering execution.
    """
    from agent.constants import MAX_DELEGATION_DEPTH, MAX_SUBTASKS_PER_TASK

    parent_task = get_task_or_404(task_id, db)

    # Check depth limit
    new_depth = parent_task.depth + 1
    if new_depth > MAX_DELEGATION_DEPTH:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum delegation depth ({MAX_DELEGATION_DEPTH}) exceeded"
        )

    # Check subtask count limit
    existing_subtask_count = db.query(Task).filter(Task.parent_id == task_id).count()
    if existing_subtask_count >= MAX_SUBTASKS_PER_TASK:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum subtasks per task ({MAX_SUBTASKS_PER_TASK}) exceeded"
        )

    # Use parent's node if not specified
    node_id = subtask.node_id or parent_task.node_id

    # Create the subtask
    db_subtask = Task(
        project_id=parent_task.project_id,
        parent_id=task_id,
        node_id=node_id,
        title=subtask.title,
        description=subtask.description,
        status="in_progress",
        depth=new_depth,
    )
    db.add(db_subtask)
    db.flush()

    # Create a default acceptance criteria for the subtask
    db.add(TaskAcceptanceCriteria(
        task_id=db_subtask.id,
        description=f"Complete: {subtask.title}",
        passed=False,
        author="system",
    ))

    # Create TaskRun record for audit
    run = TaskRun(
        task_id=db_subtask.id,
        node_id=node_id,
        status="started",
    )
    db.add(run)

    db.commit()
    db.refresh(db_subtask)

    # Trigger background execution if requested
    if trigger:
        import asyncio
        asyncio.create_task(_execute_subtask_background(db_subtask.id, run.id))

    return db_subtask


async def _execute_subtask_background(subtask_id: int, run_id: int):
    """Execute a subtask in the background.

    This function runs the agent for the subtask and updates status.
    """
    import httpx
    from database import SessionLocal

    AIDER_API_URL = os.getenv("AIDER_API_URL", "http://wfhub-v2-aider-api:8001")

    db = SessionLocal()
    try:
        subtask = db.query(Task).filter(Task.id == subtask_id).first()
        if not subtask:
            return

        run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
        if not run:
            return

        project = db.query(Project).filter(Project.id == subtask.project_id).first()
        if not project:
            return

        node = db.query(TaskNode).filter(TaskNode.id == subtask.node_id).first()
        node_name = node.name if node else "dev"
        node_prompt = node.agent_prompt if node else None

        # Build task prompt
        prompt_parts = []
        if node_prompt:
            prompt_parts.append(f"ROLE: {node_prompt}")
        prompt_parts.append(f"TASK: {subtask.title}")
        if subtask.description:
            prompt_parts.append(f"\nDESCRIPTION:\n{subtask.description}")
        prompt_parts.append("\n\nComplete this task.")

        full_prompt = "\n".join(prompt_parts)

        # Handle workspace path
        workspace_path = project.workspace_path
        if workspace_path.startswith("[%root%]"):
            workspace_name = workspace_path
        else:
            from pathlib import Path
            workspace_name = Path(workspace_path).name

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    f"{AIDER_API_URL}/api/agent/run",
                    json={
                        "task": full_prompt,
                        "workspace": workspace_name,
                        "project_id": project.id,
                        "task_id": subtask.id,
                        "max_iterations": 20,
                        "depth": subtask.depth,
                        "parent_task_id": subtask.parent_id,
                    }
                )
                result = response.json()

            success = result.get("success") or result.get("status") == "PASS"

            if success:
                subtask.status = "done"
                run.status = "completed"
            else:
                subtask.status = "failed"
                run.status = "failed"
                run.error = result.get("error") or result.get("summary")

            run.summary = result.get("summary")
            run.tool_calls = result.get("tool_calls")
            run.finished_at = datetime.utcnow()

        except Exception as e:
            subtask.status = "failed"
            run.status = "failed"
            run.error = str(e)
            run.finished_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()


@router.get("/tasks/{task_id}/subtasks", response_model=List[TaskResponse])
def list_subtasks(task_id: int, db: Session = Depends(get_db)):
    """List all subtasks of a task."""
    get_task_or_404(task_id, db)
    return db.query(Task).filter(Task.parent_id == task_id).all()


@router.get("/tasks/{task_id}/external-links", response_model=List[TaskExternalLinkResponse])
def list_task_external_links(task_id: int, db: Session = Depends(get_db)):
    """List external links for a task."""
    get_task_or_404(task_id, db)
    return (
        db.query(TaskExternalLink)
        .filter(TaskExternalLink.task_id == task_id)
        .all()
    )
