"""FastAPI app for v2 agentic system."""
import asyncio
import json
import os
import time
import re
import subprocess
import threading
import itertools
import uuid
import httpx
from collections import deque
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path

from database import get_db
from models import Project, Task, TaskComment, TaskAttachment, TaskAcceptanceCriteria

app = FastAPI(title="Agentic v2", version="2.0.0")

# CORS for websocket connections from browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

ENV_FILE_PATH = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent)).resolve() / ".env"


def get_uploads_root() -> Path:
    """Resolve uploads directory from env or default under project root."""
    root = os.getenv("UPLOADS_DIR")
    if not root:
        root = str(Path(__file__).parent / "uploads")
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


def get_git_recent_info(workspace_path: Path) -> dict:
    """Return last commit summary and files plus working changes."""
    info = {
        "last_commit_summary": None,
        "last_commit_files": [],
        "working_changes": [],
    }
    if not (workspace_path / ".git").exists():
        return info
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "log", "-1", "--name-only", "--pretty=format:%h %s"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if lines:
            info["last_commit_summary"] = lines[0]
            info["last_commit_files"] = lines[1:]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return info

    try:
        status = subprocess.run(
            ["git", "-C", str(workspace_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        changes = []
        for line in status.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                changes.append({"status": parts[0], "path": parts[1]})
        info["working_changes"] = changes
    except (subprocess.CalledProcessError, FileNotFoundError):
        return info
    return info


def get_task_or_404(task_id: int, db: Session) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def get_comment_or_404(task_id: int, comment_id: int, db: Session) -> TaskComment:
    comment = db.query(TaskComment).filter(
        TaskComment.id == comment_id,
        TaskComment.task_id == task_id,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment


def get_attachment_or_404(task_id: int, attachment_id: int, db: Session) -> TaskAttachment:
    attachment = db.query(TaskAttachment).filter(
        TaskAttachment.id == attachment_id,
        TaskAttachment.task_id == task_id,
    ).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


def get_acceptance_or_404(
    task_id: int, criteria_id: int, db: Session
) -> TaskAcceptanceCriteria:
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

# Pydantic schemas
class ProjectCreate(BaseModel):
    name: str
    workspace_path: str
    environment: str = "local"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    workspace_path: Optional[str] = None
    environment: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    workspace_path: str
    environment: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    project_id: int
    parent_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    parent_id: Optional[int]
    title: str
    description: Optional[str]
    status: str
    stage: str
    created_at: Optional[datetime]
    children: List["TaskResponse"] = []

    class Config:
        from_attributes = True


TaskResponse.model_rebuild()


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


class GitCheckoutRequest(BaseModel):
    branch: str
    create: bool = False


class GitRemoteRequest(BaseModel):
    name: str
    url: str


class GitRemoteActionRequest(BaseModel):
    remote: Optional[str] = None
    branch: Optional[str] = None


class GitUserConfigRequest(BaseModel):
    name: str
    email: str


# Root endpoint - serve chat interface
@app.get("/")
def root():
    return FileResponse("chat.html")


@app.get("/health/full")
def full_health_check():
    """Full health check for main-api dependencies."""
    import docker
    import psycopg2

    def check_db():
        try:
            conn = psycopg2.connect(
                dbname="agentic",
                user=os.getenv("POSTGRES_USER", "wfhub"),
                password=os.getenv("POSTGRES_PASSWORD", "wfhub"),
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                connect_timeout=2,
            )
            conn.close()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def check_http(url: str):
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return {"status": "ok"}
                return {"status": "error", "error": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def check_docker():
        try:
            client = docker.from_env()
            client.ping()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_container_status(container_name: str):
        try:
            client = docker.from_env()
            container = client.containers.get(container_name)
            return {"status": container.status}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    aider_url = os.getenv("AIDER_API_URL", "http://wfhub-v2-aider-api:8001")
    ollama_url = os.getenv(
        "OLLAMA_PROXY_TARGET",
        os.getenv("OLLAMA_API_BASE", "http://wfhub-v2-ollama:11434"),
    )

    result = {
        "main_api": {"status": "ok"},
        "database": check_db(),
        "aider_api": check_http(f"{aider_url}/health"),
        "ollama": check_http(f"{ollama_url}/api/tags"),
        "docker": check_docker(),
        "containers": {
            name: get_container_status(container_name)
            for name, container_name in CONTAINER_NAMES.items()
        },
    }
    ok = all(
        entry.get("status") == "ok"
        for entry in [result["database"], result["aider_api"], result["ollama"], result["docker"]]
    )
    result["overall_status"] = "ok" if ok else "degraded"
    return result


# Project endpoints
@app.get("/projects", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@app.post("/projects", response_model=ProjectResponse)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    db_project = Project(
        name=project.name,
        workspace_path=project.workspace_path,
        environment=project.environment,
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    workspace_path = resolve_workspace_path(db_project.workspace_path)
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
        if not (workspace_path / ".git").exists():
            subprocess.run(["git", "-C", str(workspace_path), "init"], check=True, capture_output=True)
            git_name = os.getenv("GIT_USER_NAME", "Aider Agent")
            git_email = os.getenv("GIT_USER_EMAIL", "aider@local")
            subprocess.run(
                ["git", "-C", str(workspace_path), "config", "user.name", git_name],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(workspace_path), "config", "user.email", git_email],
                check=True,
                capture_output=True,
            )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git init error: {exc.stderr}")
    return db_project


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: int, update: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if update.name is not None:
        project.name = update.name
    if update.workspace_path is not None:
        project.workspace_path = update.workspace_path
    if update.environment is not None:
        project.environment = update.environment

    db.commit()
    db.refresh(project)
    return project


@app.delete("/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"deleted": True}


# Task endpoints
@app.get("/projects/{project_id}/tasks", response_model=List[TaskResponse])
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


@app.post("/tasks", response_model=TaskResponse)
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

    db_task = Task(
        project_id=task.project_id,
        parent_id=task.parent_id,
        title=task.title,
        description=task.description,
        status=task.status or "backlog",
        stage=task.stage or "dev",
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if update.title is not None:
        task.title = update.title
    if update.description is not None:
        task.description = update.description
    if update.status is not None:
        task.status = update.status
    if update.stage is not None:
        task.stage = update.stage

    db.commit()
    db.refresh(task)
    return task


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"deleted": True, "task_id": task_id}


# Comment endpoints
@app.get("/tasks/{task_id}/comments", response_model=List[CommentResponse])
def list_task_comments(task_id: int, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    return (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )


@app.post("/tasks/{task_id}/comments", response_model=CommentResponse)
def create_task_comment(task_id: int, comment: CommentCreate, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    author = (comment.author or "").strip() or "human"
    db_comment = TaskComment(task_id=task_id, author=author, body=comment.body)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


@app.patch("/tasks/{task_id}/comments/{comment_id}", response_model=CommentResponse)
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


@app.delete("/tasks/{task_id}/comments/{comment_id}")
def delete_task_comment(task_id: int, comment_id: int, db: Session = Depends(get_db)):
    comment = get_comment_or_404(task_id, comment_id, db)
    db.delete(comment)
    db.commit()
    return {"deleted": True, "comment_id": comment_id}


# Attachment endpoints
@app.get("/tasks/{task_id}/attachments", response_model=List[AttachmentResponse])
def list_task_attachments(
    task_id: int, comment_id: Optional[int] = None, db: Session = Depends(get_db)
):
    get_task_or_404(task_id, db)
    query = db.query(TaskAttachment).filter(TaskAttachment.task_id == task_id)
    if comment_id is not None:
        query = query.filter(TaskAttachment.comment_id == comment_id)
    return query.order_by(TaskAttachment.created_at.asc()).all()


@app.post("/tasks/{task_id}/attachments", response_model=AttachmentResponse)
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


@app.get("/tasks/{task_id}/attachments/{attachment_id}/download")
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


@app.delete("/tasks/{task_id}/attachments/{attachment_id}")
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


# Acceptance criteria endpoints
@app.get("/tasks/{task_id}/acceptance", response_model=List[AcceptanceCriteriaResponse])
def list_task_acceptance(task_id: int, db: Session = Depends(get_db)):
    get_task_or_404(task_id, db)
    return (
        db.query(TaskAcceptanceCriteria)
        .filter(TaskAcceptanceCriteria.task_id == task_id)
        .order_by(TaskAcceptanceCriteria.created_at.asc())
        .all()
    )


@app.post("/tasks/{task_id}/acceptance", response_model=AcceptanceCriteriaResponse)
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


@app.patch("/tasks/{task_id}/acceptance/{criteria_id}", response_model=AcceptanceCriteriaResponse)
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


@app.delete("/tasks/{task_id}/acceptance/{criteria_id}")
def delete_task_acceptance(task_id: int, criteria_id: int, db: Session = Depends(get_db)):
    criteria = get_acceptance_or_404(task_id, criteria_id, db)
    db.delete(criteria)
    db.commit()
    return {"deleted": True, "criteria_id": criteria_id}


@app.get("/tasks/{task_id}/context")
def get_task_context(task_id: int, db: Session = Depends(get_db)):
    task = get_task_or_404(task_id, db)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    git_info = get_git_recent_info(workspace_path) if workspace_path.exists() else {
        "last_commit_summary": None,
        "last_commit_files": [],
        "working_changes": [],
    }

    acceptance = (
        db.query(TaskAcceptanceCriteria)
        .filter(TaskAcceptanceCriteria.task_id == task_id)
        .order_by(TaskAcceptanceCriteria.created_at.asc())
        .all()
    )
    attachments = (
        db.query(TaskAttachment)
        .filter(TaskAttachment.task_id == task_id)
        .order_by(TaskAttachment.created_at.asc())
        .all()
    )
    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task_id)
        .order_by(TaskComment.updated_at.desc())
        .limit(3)
        .all()
    )

    attachments_payload = []
    for item in attachments:
        payload = item.to_dict()
        payload["description"] = item.filename
        attachments_payload.append(payload)

    context = {
        "task": {
            "id": task.id,
            "project_id": task.project_id,
            "parent_id": task.parent_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "stage": task.stage,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        },
        "acceptance_criteria": [item.to_dict() for item in acceptance],
        "attachments": attachments_payload,
        "comments_recent": [item.to_dict() for item in comments],
        "git": git_info,
        "mcp": {
            "notes": "Use these endpoints for more context if needed.",
            "endpoints": {
                "task": f"/tasks/{task.id}",
                "comments": f"/tasks/{task.id}/comments",
                "attachments": f"/tasks/{task.id}/attachments",
                "acceptance": f"/tasks/{task.id}/acceptance",
                "project_files": f"/projects/{project.id}/files",
                "git_status": f"/projects/{project.id}/git/status",
            },
        },
    }
    return context


@app.post("/tasks/{task_id}/trigger")
def trigger_task(task_id: int, db: Session = Depends(get_db)):
    """Manually trigger the Aider agent for a task."""
    from pathlib import Path

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

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
    try:
        from agent.aider_runner import run_agent

        result = run_agent(
            workspace_name=workspace_name,
            task_title=task.title,
            task_description=task.description or "",
            task_id=task.id,
            stage=task.stage,
        )

        # Update task status based on result
        if result.get("status") == "PASS":
            task.status = "done"
        else:
            task.status = "failed"
        db.commit()

        return {"triggered": True, "task_id": task_id, "result": result}

    except Exception as e:
        task.status = "failed"
        db.commit()
        return {"triggered": False, "task_id": task_id, "error": str(e)}


# Director endpoints
@app.get("/director/status")
def director_status():
    """Get director daemon status."""
    # TODO: Implement actual status check
    return {"running": False, "message": "Director not implemented yet"}


@app.post("/director/cycle")
def director_cycle(db: Session = Depends(get_db)):
    """Run one director cycle manually."""
    # TODO: Implement director cycle
    return {"message": "Director cycle not implemented yet"}


@app.post("/ops/restart/{service}")
def restart_service(service: str):
    """Restart a safe subset of containers via Docker."""
    import docker

    allowed = {"aider", "ollama"}
    if service not in allowed:
        raise HTTPException(status_code=404, detail="Service not supported for restart")

    container_name = CONTAINER_NAMES.get(service)
    if not container_name:
        raise HTTPException(status_code=404, detail="Unknown container")

    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        return {"success": True, "service": service, "container": container_name}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _restart_services(services: list[str]) -> dict:
    import docker

    allowed = {"aider", "ollama", "main", "db"}
    invalid = [s for s in services if s not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported services: {', '.join(invalid)}")

    client = docker.from_env()
    results = {}

    def restart_now(service_name: str):
        container_name = CONTAINER_NAMES.get(service_name)
        if not container_name:
            results[service_name] = {"success": False, "error": "Unknown container"}
            return
        try:
            container = client.containers.get(container_name)
            container.restart(timeout=10)
            results[service_name] = {"success": True, "container": container_name}
        except docker.errors.NotFound:
            results[service_name] = {"success": False, "error": "Container not found"}
        except Exception as exc:
            results[service_name] = {"success": False, "error": str(exc)}

    # Restart non-main services first to avoid self-restart mid-request
    for name in services:
        if name != "main":
            restart_now(name)

    if "main" in services:
        def delayed_restart():
            time.sleep(1)
            restart_now("main")
        threading.Thread(target=delayed_restart, daemon=True).start()
        results["main"] = {"success": True, "container": CONTAINER_NAMES.get("main"), "delayed": True}

    return results


def _parse_env_line(line: str) -> tuple[str, str, str, str] | None:
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        return None
    prefix, rest = line.split("=", 1)
    key = prefix.strip()
    if not key:
        return None
    value = rest.rstrip("\n")
    return key, prefix + "=", value, "\n" if line.endswith("\n") else ""


def _read_env_file() -> list[dict]:
    if not ENV_FILE_PATH.exists():
        return []
    entries = []
    with ENV_FILE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle.readlines():
            stripped = line.rstrip("\n")
            if not stripped:
                entries.append({"type": "blank"})
                continue
            if stripped.lstrip().startswith("#") or "=" not in stripped:
                entries.append({"type": "comment", "value": stripped})
                continue
            parsed = _parse_env_line(stripped)
            if not parsed:
                entries.append({"type": "comment", "value": stripped})
                continue
            key, _, value, _ = parsed
            entries.append({"type": "pair", "key": key, "value": value})
    return entries


def _write_env_file(updates: dict) -> list[str]:
    if not ENV_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail=".env not found")

    updated_keys = []
    seen_keys = set()
    new_lines = []

    backup_text = ENV_FILE_PATH.read_text(encoding="utf-8")
    backup_path = ENV_FILE_PATH.with_suffix(".env_bak.txt")
    backup_path.write_text(backup_text, encoding="utf-8")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    history_path = ENV_FILE_PATH.with_name(f".env_bak_{timestamp}.txt")
    history_path.write_text(backup_text, encoding="utf-8")
    with ENV_FILE_PATH.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    for line in lines:
        parsed = _parse_env_line(line)
        if not parsed:
            new_lines.append(line)
            continue
        key, prefix, value, newline = parsed
        seen_keys.add(key)
        if key in updates:
            new_value = str(updates[key])
            new_lines.append(f"{prefix}{new_value}{newline}")
            updated_keys.append(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen_keys:
            new_lines.append(f"{key}={value}\n")
            updated_keys.append(key)

    ENV_FILE_PATH.write_text("".join(new_lines), encoding="utf-8")
    return updated_keys


@app.get("/api/env")
def get_env_settings():
    """Return .env entries for editing."""
    return {"success": True, "entries": _read_env_file()}


@app.post("/api/env")
def update_env_settings(payload: dict):
    """Update .env values and restart services if requested."""
    updates = payload.get("updates", {})
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="updates must be an object")

    updated_keys = _write_env_file(updates)
    services = payload.get("restart_services", [])
    if services:
        restart_results = _restart_services(services)
    else:
        restart_results = {}
    return {"success": True, "updated_keys": updated_keys, "restarted": restart_results}


# ============================================================================
# File Browser for Workspaces
# ============================================================================

import os
from pathlib import Path


def get_workspaces_root() -> Path:
    """Resolve WORKSPACES_DIR, supporting relative paths via PROJECT_ROOT."""
    root_value = os.getenv("WORKSPACES_DIR", "/workspaces")
    root_path = Path(root_value)
    if not root_path.is_absolute():
        base_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent)).resolve()
        root_path = (base_root / root_path).resolve()
    return root_path


def resolve_workspace_path(workspace_path: str) -> Path:
    """Resolve workspace path, supporting [%root%] variable.

    Args:
        workspace_path: Workspace path from project, can be:
            - "[%root%]" -> resolves to PROJECT_ROOT
            - "[%root%]/subdir" -> resolves to PROJECT_ROOT/subdir
            - Regular workspace name -> joined with WORKSPACES_DIR

    Returns:
        Absolute Path to the workspace directory
    """
    if workspace_path.startswith("[%root%]"):
        # Get PROJECT_ROOT from env, fallback to /v2
        root = os.environ.get("PROJECT_ROOT", "/v2")
        resolved = workspace_path.replace("[%root%]", root)
        return Path(resolved)

    # Default: extract workspace name and join with WORKSPACES_DIR
    workspace_name = Path(workspace_path).name
    return get_workspaces_root() / workspace_name


@app.get("/projects/{project_id}/files")
def list_project_files(project_id: int, db: Session = Depends(get_db)):
    """List files in a project's workspace as a tree structure."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get workspace path - supports [%root%] variable
    workspace_path = resolve_workspace_path(project.workspace_path)
    # For display purposes, keep the original path notation
    display_name = project.workspace_path if project.workspace_path.startswith("[%root%]") else workspace_path.name

    if not workspace_path.exists():
        return {"project_id": project_id, "workspace": display_name, "files": [], "error": "Workspace not found"}

    def build_tree(path: Path, max_depth: int = 3, current_depth: int = 0) -> dict:
        """Build a file tree structure."""
        if current_depth >= max_depth:
            return None

        result = {
            "name": path.name,
            "path": str(path.relative_to(workspace_path)),
            "type": "directory" if path.is_dir() else "file",
        }

        if path.is_dir():
            children = []
            try:
                children_entries = [
                    child for child in path.iterdir()
                    if child.name not in ['node_modules', '__pycache__', 'venv']
                ]
                for child in sorted(children_entries, key=lambda entry: (entry.is_file(), entry.name.lower())):
                    child_tree = build_tree(child, max_depth, current_depth + 1)
                    if child_tree:
                        children.append(child_tree)
            except PermissionError:
                pass
            result["children"] = children

        return result

    tree = build_tree(workspace_path)
    return {
        "project_id": project_id,
        "workspace": display_name,
        "files": tree.get("children", []) if tree else []
    }


def _validate_branch_name(branch: str) -> None:
    if not branch or not isinstance(branch, str):
        raise HTTPException(status_code=400, detail="branch required")
    if branch.startswith("-") or branch in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid branch name")
    if ".." in branch or "@" in branch or "~" in branch or "\\" in branch:
        raise HTTPException(status_code=400, detail="invalid branch name")
    if not re.match(r"^[A-Za-z0-9._/-]+$", branch):
        raise HTTPException(status_code=400, detail="invalid branch name")


@app.get("/projects/{project_id}/git/branches")
def list_git_branches(project_id: int, db: Session = Depends(get_db)):
    """List git branches for a project's workspace."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        return {"branches": [], "current": None}

    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "branch", "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        branches = []
        current = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("*"):
                current = line.replace("*", "").strip()
                branches.append(current)
            else:
                branches.append(line)
        return {"branches": branches, "current": current}
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.get("/projects/{project_id}/git/status")
def git_status(project_id: int, db: Session = Depends(get_db)):
    """Get git status, branches, and remotes for a workspace."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        return {"branches": [], "current": None, "remotes": [], "user_name": "", "user_email": ""}

    try:
        branches_result = subprocess.run(
            ["git", "-C", str(workspace_path), "branch", "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        branches = []
        current = None
        for line in branches_result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("*"):
                current = line.replace("*", "").strip()
                branches.append(current)
            else:
                branches.append(line)

        remotes_result = subprocess.run(
            ["git", "-C", str(workspace_path), "remote", "-v"],
            capture_output=True,
            text=True,
            check=True,
        )
        remotes = {}
        for line in remotes_result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name, url = parts[0], parts[1]
                if name not in remotes:
                    remotes[name] = url

        user_name = subprocess.run(
            ["git", "-C", str(workspace_path), "config", "--get", "user.name"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        user_email = subprocess.run(
            ["git", "-C", str(workspace_path), "config", "--get", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

        return {
            "branches": branches,
            "current": current,
            "remotes": [{"name": name, "url": url} for name, url in remotes.items()],
            "user_name": user_name,
            "user_email": user_email,
        }
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.post("/projects/{project_id}/git/remote")
def add_git_remote(
    project_id: int,
    payload: GitRemoteRequest,
    db: Session = Depends(get_db),
):
    """Add or update a git remote."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        raise HTTPException(status_code=400, detail="Workspace is not a git repo")

    _validate_branch_name(payload.name)
    try:
        subprocess.run(
            ["git", "-C", str(workspace_path), "remote", "remove", payload.name],
            capture_output=True,
            text=True,
            check=False,
        )
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "remote", "add", payload.name, payload.url],
            capture_output=True,
            text=True,
            check=True,
        )
        return {"success": True, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.post("/projects/{project_id}/git/pull")
def pull_git_remote(
    project_id: int,
    payload: GitRemoteActionRequest,
    db: Session = Depends(get_db),
):
    """Pull from a git remote."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        raise HTTPException(status_code=400, detail="Workspace is not a git repo")

    remote = payload.remote or "origin"
    branch = payload.branch
    cmd = ["git", "-C", str(workspace_path), "pull", remote]
    if branch:
        cmd.append(branch)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"success": True, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.post("/projects/{project_id}/git/push")
def push_git_remote(
    project_id: int,
    payload: GitRemoteActionRequest,
    db: Session = Depends(get_db),
):
    """Push to a git remote."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        raise HTTPException(status_code=400, detail="Workspace is not a git repo")

    remote = payload.remote or "origin"
    branch = payload.branch
    cmd = ["git", "-C", str(workspace_path), "push", remote]
    if branch:
        cmd.append(branch)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"success": True, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.post("/projects/{project_id}/git/init")
def init_git_repo(project_id: int, db: Session = Depends(get_db)):
    """Initialize a git repo in the project's workspace if missing."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_path), "init"],
            capture_output=True,
            text=True,
            check=True
        )
        git_name = os.getenv("GIT_USER_NAME", "Aider Agent")
        git_email = os.getenv("GIT_USER_EMAIL", "aider@local")
        subprocess.run(
            ["git", "-C", str(workspace_path), "config", "user.name", git_name],
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(workspace_path), "config", "user.email", git_email],
            capture_output=True,
            text=True,
            check=True,
        )
        return {"success": True, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.post("/projects/{project_id}/git/config")
def set_git_user_config(
    project_id: int,
    payload: GitUserConfigRequest,
    db: Session = Depends(get_db),
):
    """Set git user.name and user.email for the workspace repo."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        raise HTTPException(status_code=400, detail="Workspace is not a git repo")

    if not payload.name or not payload.email:
        raise HTTPException(status_code=400, detail="name and email required")

    try:
        name_result = subprocess.run(
            ["git", "-C", str(workspace_path), "config", "user.name", payload.name],
            capture_output=True,
            text=True,
            check=True,
        )
        email_result = subprocess.run(
            ["git", "-C", str(workspace_path), "config", "user.email", payload.email],
            capture_output=True,
            text=True,
            check=True,
        )
        return {
            "success": True,
            "stdout": "\n".join([name_result.stdout, email_result.stdout]).strip(),
            "stderr": "\n".join([name_result.stderr, email_result.stderr]).strip(),
        }
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.post("/projects/{project_id}/git/checkout")
def checkout_git_branch(
    project_id: int,
    payload: GitCheckoutRequest,
    db: Session = Depends(get_db),
):
    """Checkout (or create) a git branch for a project's workspace."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = resolve_workspace_path(project.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not (workspace_path / ".git").exists():
        raise HTTPException(status_code=400, detail="Workspace is not a git repo")

    _validate_branch_name(payload.branch)

    cmd = ["git", "-C", str(workspace_path), "checkout"]
    if payload.create:
        cmd.append("-b")
    cmd.append(payload.branch)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        current = subprocess.run(
            ["git", "-C", str(workspace_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return {"success": True, "current": current, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc.stderr}")


@app.get("/projects/{project_id}/file/{file_path:path}")
def get_file_content(project_id: int, file_path: str, db: Session = Depends(get_db)):
    """Get raw file content for viewing in browser."""
    from fastapi.responses import PlainTextResponse

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get workspace path - supports [%root%] variable
    workspace_path = resolve_workspace_path(project.workspace_path)

    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Build full file path
    full_path = workspace_path / file_path

    # Security: ensure path stays within workspace
    try:
        full_path = full_path.resolve()
        workspace_path = workspace_path.resolve()
        if not str(full_path).startswith(str(workspace_path)):
            raise HTTPException(status_code=403, detail="Access denied: path outside workspace")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
        return PlainTextResponse(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")


# ============================================================================
# Container Log Streaming via WebSocket
# ============================================================================

# Container names to stream logs from
CONTAINER_NAMES = {
    "ollama": "wfhub-v2-ollama",
    "aider": "wfhub-v2-aider-api",
    "main": "wfhub-v2-main-api",
    "db": "wfhub-v2-db",
}

INTERNAL_LOG_SOURCES = {"ollama_http"}
OLLAMA_HTTP_LOG_BUFFER = deque(maxlen=500)
OLLAMA_HTTP_CLIENTS = set()
OLLAMA_HTTP_LOG_LOCK = asyncio.Lock()
OLLAMA_HTTP_REQUEST_ID = itertools.count(1)
OLLAMA_HTTP_LOG_MAX_BYTES = int(os.getenv("OLLAMA_HTTP_LOG_MAX_BYTES", "8192"))
# 0 = no truncation, any positive number = character limit
OLLAMA_HTTP_LOG_TRUNCATE_LIMIT = int(os.getenv("OLLAMA_HTTP_LOG_TRUNCATE_LIMIT", "0"))


def _truncate_text(text: str, limit: int | None = None) -> str:
    if not text:
        return ""
    if limit is None:
        limit = OLLAMA_HTTP_LOG_TRUNCATE_LIMIT
    flat = " ".join(text.split())
    if limit > 0 and len(flat) > limit:
        return f"{flat[:limit]}..."
    return flat


def _format_ollama_request_summary(method: str, path: str, body: bytes) -> str:
    summary = f"{method} /{path}"
    if not body:
        return summary
    try:
        payload = json.loads(body)
    except Exception:
        return f"{summary} body={len(body)} bytes"
    details = []
    model = payload.get("model")
    if model:
        details.append(f"model={model}")
    if "stream" in payload:
        details.append(f"stream={payload.get('stream')}")
    if "prompt" in payload:
        details.append(f'prompt="{_truncate_text(str(payload.get("prompt", "")))}"')
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last_msg = messages[-1].get("content", "")
        details.append(f'messages={len(messages)} last="{_truncate_text(str(last_msg))}"')
    if details:
        return f"{summary} " + " ".join(details)
    return summary


def _extract_ollama_output_snippet(snippet_text: str) -> str:
    if not snippet_text:
        return ""
    for line in reversed([l for l in snippet_text.splitlines() if l.strip()]):
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if "response" in payload:
            return _truncate_text(str(payload.get("response", "")))
        message = payload.get("message")
        if isinstance(message, dict) and "content" in message:
            return _truncate_text(str(message.get("content", "")))
        if "error" in payload:
            return _truncate_text(str(payload.get("error", "")))
    return _truncate_text(snippet_text)


async def append_ollama_http_log(line: str) -> None:
    async with OLLAMA_HTTP_LOG_LOCK:
        OLLAMA_HTTP_LOG_BUFFER.append(line)
        stale = []
        for ws in list(OLLAMA_HTTP_CLIENTS):
            try:
                await ws.send_text(line)
            except Exception:
                stale.append(ws)
        for ws in stale:
            OLLAMA_HTTP_CLIENTS.discard(ws)


async def stream_container_logs(websocket: WebSocket, container_name: str):
    """Stream logs from a Docker container via WebSocket without blocking the event loop."""
    import docker
    import queue
    import threading

    log_queue: "queue.Queue[bytes | None]" = queue.Queue()
    stop_event = threading.Event()

    def _producer():
        try:
            client = docker.from_env()
            container = client.containers.get(container_name)
            for log_line in container.logs(stream=True, follow=True, tail=100):
                if stop_event.is_set():
                    break
                log_queue.put(log_line)
        except Exception:
            log_queue.put(None)
        finally:
            log_queue.put(None)

    thread = threading.Thread(target=_producer, daemon=True)
    thread.start()

    try:
        while True:
            log_line = await asyncio.to_thread(log_queue.get)
            if log_line is None:
                break
            line = log_line.decode("utf-8", errors="replace").strip()
            if line:
                await websocket.send_text(line)
    except WebSocketDisconnect:
        stop_event.set()
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {str(e)}")
        except Exception:
            pass
    finally:
        stop_event.set()


@app.websocket("/ws/logs/{container}")
async def websocket_logs(websocket: WebSocket, container: str):
    """WebSocket endpoint to stream container logs.

    Usage: ws://localhost:8002/ws/logs/ollama
    Available containers: ollama, aider, main, db, ollama_http
    """
    await websocket.accept()

    if container in INTERNAL_LOG_SOURCES:
        try:
            for line in list(OLLAMA_HTTP_LOG_BUFFER):
                await websocket.send_text(line)
            OLLAMA_HTTP_CLIENTS.add(websocket)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            OLLAMA_HTTP_CLIENTS.discard(websocket)
        return

    container_name = CONTAINER_NAMES.get(container)
    if not container_name:
        await websocket.send_text(f"Unknown container: {container}")
        await websocket.send_text(
            f"Available: {', '.join(sorted(CONTAINER_NAMES.keys() | INTERNAL_LOG_SOURCES))}"
        )
        await websocket.close()
        return

    try:
        await websocket.send_text(f"=== Streaming logs from {container_name} ===")
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close()
        return

    try:
        await stream_container_logs(websocket, container_name)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {str(e)}")
        except Exception:
            pass


@app.get("/logs/{container}")
async def get_recent_logs(container: str, lines: int = 100):
    """Get recent logs from a container (non-streaming)."""
    import docker

    if container in INTERNAL_LOG_SOURCES:
        logs = "\n".join(list(OLLAMA_HTTP_LOG_BUFFER)[-lines:])
        return {"container": container, "lines": lines, "logs": logs}

    container_name = CONTAINER_NAMES.get(container)
    if not container_name:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown container: {container}. Available: "
                f"{', '.join(sorted(CONTAINER_NAMES.keys() | INTERNAL_LOG_SOURCES))}"
            ),
        )

    try:
        client = docker.from_env()
        container_obj = client.containers.get(container_name)
        logs = container_obj.logs(tail=lines).decode("utf-8", errors="replace")
        return {"container": container_name, "lines": lines, "logs": logs}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/ollama/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_ollama(path: str, request: Request):
    """Proxy Ollama API calls and log request/response details."""
    target_base = os.getenv(
        "OLLAMA_PROXY_TARGET",
        os.getenv("OLLAMA_API_BASE", "http://wfhub-v2-ollama:11434"),
    ).rstrip("/")
    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    request_id = next(OLLAMA_HTTP_REQUEST_ID)
    body = await request.body()
    request_summary = _format_ollama_request_summary(request.method, path, body)
    await append_ollama_http_log(f"[ollama-http] -> {request_id} {request_summary}")
    start_time = time.monotonic()

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }

    client = httpx.AsyncClient(timeout=None)
    stream = client.stream(
        request.method,
        target_url,
        content=body or None,
        headers=headers,
    )
    try:
        response = await stream.__aenter__()
    except Exception as e:
        await client.aclose()
        await append_ollama_http_log(f"[ollama-http] !! {request_id} proxy_error={e}")
        raise HTTPException(status_code=502, detail="Failed to reach Ollama") from e

    response_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in {"transfer-encoding", "connection", "content-length"}
    }

    async def stream_response():
        snippet = bytearray()
        total_bytes = 0
        try:
            async for chunk in response.aiter_bytes():
                total_bytes += len(chunk)
                if len(snippet) < OLLAMA_HTTP_LOG_MAX_BYTES:
                    snippet.extend(chunk[:OLLAMA_HTTP_LOG_MAX_BYTES - len(snippet)])
                yield chunk
        finally:
            duration = time.monotonic() - start_time
            snippet_text = snippet.decode("utf-8", errors="replace")
            output = _extract_ollama_output_snippet(snippet_text)
            output_part = f' output="{output}"' if output else ""
            await append_ollama_http_log(
                f"[ollama-http] <- {request_id} {response.status_code} "
                f"{duration:.2f}s bytes={total_bytes}{output_part}"
            )
            await response.aclose()
            await stream.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(
        stream_response(),
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
