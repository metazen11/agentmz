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

@app.get("/")
def root():
    return FileResponse("chat.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
