import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx # NEW
from pydantic import BaseModel # NEW

from database import get_db
from models import Project
from routers.tasks import get_task_or_404
from routers.nodes import get_node_or_404

router = APIRouter()

# AIDER_API_URL can be read from environment variable or config
AIDER_API_BASE_URL = os.getenv("AIDER_API_URL", "http://wfhub-v2-aider-api:8001") # Using docker-compose service name for internal communication

class AgentChatRequest(BaseModel):
    prompt: str
    workspace: str
    project_id: Optional[int] = None
    chat_mode: bool = False
    image_context: Optional[str] = None

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

@router.post("/api/agent/chat")
async def chat_with_agent(
    request: AgentChatRequest,
    db: Session = Depends(get_db) # Keep for consistency, though not used for chat_mode context yet
):
    """
    Proxies a chat message from the frontend to the Aider API.
    The Main API builds the appropriate system prompt for the Aider API.
    """
    if not request.workspace:
        raise HTTPException(status_code=400, detail="Workspace is required")

    # 1. Fetch project details (if project_id provided)
    project_details = None
    if request.project_id:
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if project:
            project_details = {
                "id": project.id,
                "name": project.name,
                "workspace_path": project.workspace_path,
                "environment": project.environment,
            }
    
    # 2. Construct user message (including image_context if present)
    user_message_content = request.prompt
    if request.image_context:
        user_message_content = f"{request.image_context}\n\n{user_message_content}"

    # 3. Prepare payload for Aider API's /api/agent/run
    aider_payload = {
        "task": user_message_content,
        "workspace": request.workspace,
        "project_id": request.project_id,
        "chat_mode": request.chat_mode,
    }

    # 4. Route to appropriate endpoint
    async with httpx.AsyncClient() as client:
        try:
            if request.chat_mode:
                # For chat mode, use the agent loop for conversational responses
                chat_system_prompt = """You are a helpful coding assistant. Respond to user questions or commands directly.
If you need to perform actions, use the available tools:
- grep: Search for patterns in files
- glob: Find files by pattern
- read: Read file contents
- bash: Run a shell command
- edit: Modify existing code files
- write: Create new files
"""
                if project_details:
                    chat_system_prompt += f"\n\nYou are currently working in project '{project_details['name']}' ({request.workspace})."
                    chat_system_prompt += f"\nWorkspace Path: {project_details['workspace_path']}"
                aider_payload["system_prompt_override"] = chat_system_prompt

                aider_response = await client.post(
                    f"{AIDER_API_BASE_URL}/api/agent/run",
                    json=aider_payload,
                    timeout=120
                )
            else:
                # For task execution, use aider CLI directly
                aider_execute_payload = {
                    "workspace": request.workspace,
                    "prompt": user_message_content,
                    "files": [],  # Let aider auto-detect files
                    "timeout": 300  # 5 minute timeout for tasks
                }
                aider_response = await client.post(
                    f"{AIDER_API_BASE_URL}/api/aider/execute",
                    json=aider_execute_payload,
                    timeout=330  # Slightly longer than task timeout
                )

            aider_response.raise_for_status()
            result = aider_response.json()

            # Normalize response format for frontend
            if not request.chat_mode:
                # Convert aider/execute response to expected format
                return {
                    "success": result.get("success", False),
                    "status": "PASS" if result.get("success") else "FAIL",
                    "summary": result.get("output", "")[:500] if result.get("success") else result.get("error", "Aider failed"),
                    "output": result.get("output", ""),
                    "error": result.get("error"),
                    "model": result.get("model")
                }
            return result

        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Aider API error: {e.response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Could not connect to Aider API: {str(e)}")