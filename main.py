"""FastAPI app for v2 agentic system."""
import asyncio
import json
import os
import time
import itertools
import httpx
from collections import deque
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Project, Task

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


# ============================================================================
# File Browser for Workspaces
# ============================================================================

import os
from pathlib import Path

WORKSPACES_DIR = "/workspaces"


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
    return Path(WORKSPACES_DIR) / workspace_name


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


def _truncate_text(text: str, limit: int = 200) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) > limit:
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
