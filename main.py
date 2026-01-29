"""FastAPI app for v2 agentic system."""
import asyncio
import os
import time
import threading
import itertools
import httpx
from collections import deque
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path

from database import get_db

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

from routers import (
    projects,
    tasks,
    acceptance_criteria,
    nodes,
    comments,
    attachments,
    task_runs,
    integrations,
    workspace,
    operations,
    logs,
    help_agents,
    terminal,
)

app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(acceptance_criteria.router, tags=["acceptance_criteria"])
app.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
app.include_router(comments.router, tags=["comments"])
app.include_router(attachments.router, tags=["attachments"])
app.include_router(task_runs.router, tags=["task_runs"])
app.include_router(integrations.router, tags=["integrations"])
app.include_router(workspace.router, tags=["workspace"])
app.include_router(operations.router, tags=["operations"])
app.include_router(logs.router, tags=["logs"])
app.include_router(help_agents.router, tags=["help"])
app.include_router(terminal.router, tags=["terminal"])

@app.get("/health")
def health():
    """Simple health check."""
    return {"status": "ok", "service": "main-api"}


@app.get("/health/full")
async def health_full():
    """Full health check including all services."""
    import httpx

    aider_status = {"status": "unknown"}
    ollama_status = {"status": "unknown"}

    # Check aider-api
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            aider_res = await client.get("http://wfhub-v2-aider-api:8001/health")
            if aider_res.status_code == 200:
                aider_status = {"status": "ok"}
            else:
                aider_status = {"status": "error", "code": aider_res.status_code}
    except Exception as e:
        aider_status = {"status": "error", "error": str(e)}

    # Check ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            ollama_res = await client.get("http://wfhub-v2-ollama:11434/api/tags")
            if ollama_res.status_code == 200:
                ollama_status = {"status": "ok"}
            else:
                ollama_status = {"status": "error", "code": ollama_res.status_code}
    except Exception as e:
        ollama_status = {"status": "error", "error": str(e)}

    # Overall status
    all_ok = aider_status.get("status") == "ok" and ollama_status.get("status") == "ok"

    return {
        "overall_status": "ok" if all_ok else "degraded",
        "status": "ok",
        "service": "main-api",
        "version": "2.0.0",
        "aider_api": aider_status,
        "ollama": ollama_status,
    }


@app.get("/config")
def get_config():
    """Return application configuration for frontend."""
    # HOST_PROJECT_ROOT is the host machine path (for VS Code URLs in browser)
    # PROJECT_ROOT is /app inside container
    host_root = os.getenv("HOST_PROJECT_ROOT", os.getenv("PROJECT_ROOT", ""))
    workspaces_dir = os.getenv("WORKSPACES_DIR", "workspaces")

    # Build workspaces path using host path
    if host_root:
        workspaces_path = f"{host_root}/{workspaces_dir}".replace("//", "/")
    else:
        workspaces_path = workspaces_dir

    return {
        "project_root": host_root,
        "workspaces_dir": workspaces_path,
        "default_workspace": os.getenv("DEFAULT_WORKSPACE", "poc"),
    }


@app.get("/")
def root():
    return FileResponse("chat.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
