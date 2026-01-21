import os
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Project
from routers.tasks import get_task_or_404
from routers.nodes import get_node_or_404

router = APIRouter()


@router.get("/help/agents")
def help_service_for_agents(
    project_id: Optional[int] = None,
    task_id: Optional[int] = None,
    node_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Provide agents with system-agnostic instructions for querying project/task data."""
    project = None
    task = None
    node = None
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
    if task_id:
        task = get_task_or_404(task_id, db)
        project = project or db.query(Project).filter(Project.id == task.project_id).first()
    if node_id:
        node = get_node_or_404(node_id, db)
    response = {
        "service": "helpServiceForAgents",
        "description": (
            "Use this endpoint to remind yourself how to query workspace state, "
            "task metadata, and related attachments/comments. "
            "Include project_id or task_id to tailor the response."
        ),
        "system_domain": os.getenv("APP_URL", "https://wfhub.localhost"),
        "main_api_url": os.getenv("MAIN_API_URL", "http://wfhub-v2-main-api:8002"),
        "endpoints": {
            "project": "/projects/{project_id}",
            "task": "/tasks/{task_id}",
            "comments": "/tasks/{task_id}/comments",
            "attachments": "/tasks/{task_id}/attachments",
            "acceptance": "/tasks/{task_id}/acceptance",
            "runs": "/tasks/{task_id}/runs",
            "files": "/projects/{project_id}/files",
            "git_status": "/projects/{project_id}/git/status",
            "help": "/help/agents",
        },
        "advice": {
            "query_strategy": (
                "Fetch more details only when objective/criteria require it. "
                "Use the endpoints above with the provided identifiers."
            ),
        },
    }
    if project:
        response["project"] = {
            "id": project.id,
            "name": project.name,
            "workspace_path": project.workspace_path,
            "environment": project.environment,
        }
    if task:
        response["task"] = {
            "id": task.id,
            "title": task.title,
            "node_id": task.node_id,
            "node_name": task.node_name,
        }
    if node:
        response["node"] = {
            "id": node.id,
            "name": node.name,
            "agent_prompt": node.agent_prompt,
        }
    return response
