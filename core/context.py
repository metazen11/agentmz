"""Builds context payloads for tasks."""
import json
import subprocess
from pathlib import Path
from sqlalchemy.orm import Session
from models import Task, Project, TaskAcceptanceCriteria, TaskAttachment, TaskComment
from env_utils import resolve_workspace_path

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


def _build_node_prompt_payload(node) -> dict | None:
    """Return only node fields needed for agent prompting."""
    if not node:
        return None
    return {
        "id": node.id,
        "name": node.name,
        "agent_prompt": node.agent_prompt,
    }


def build_task_context_payload(task: Task, project: Project, db: Session) -> dict:
    workspace_path = resolve_workspace_path(project.workspace_path)
    git_info = get_git_recent_info(workspace_path) if workspace_path.exists() else {
        "last_commit_summary": None,
        "last_commit_files": [],
        "working_changes": [],
    }

    acceptance = (
        db.query(TaskAcceptanceCriteria)
        .filter(TaskAcceptanceCriteria.task_id == task.id)
        .order_by(TaskAcceptanceCriteria.created_at.asc())
        .all()
    )
    attachments = (
        db.query(TaskAttachment)
        .filter(TaskAttachment.task_id == task.id)
        .order_by(TaskAttachment.created_at.asc())
        .all()
    )
    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task.id)
        .order_by(TaskComment.updated_at.desc())
        .limit(3)
        .all()
    )

    attachments_payload = []
    for item in attachments:
        payload = item.to_dict()
        payload["description"] = item.filename
        attachments_payload.append(payload)

    node_payload = _build_node_prompt_payload(task.node)
    context = {
        "task": {
            "id": task.id,
            "project_id": task.project_id,
            "parent_id": task.parent_id,
            "node_id": task.node_id,
            "node_name": task.node_name,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        },
        "node": node_payload,
        "acceptance_criteria": [item.to_dict() for item in acceptance],
        "attachments": attachments_payload,
        "comments_recent": [item.to_dict() for item in comments],
        "git": git_info,
        "mcp": {
            "notes": "Use these endpoints for more context or to report results.",
            "endpoints": {
                "task": f"/tasks/{task.id}",
                "comments": f"/tasks/{task.id}/comments",
                "attachments": f"/tasks/{task.id}/attachments",
                "acceptance": f"/tasks/{task.id}/acceptance",
                "runs": f"/tasks/{task.id}/runs",
                "project_files": f"/projects/{project.id}/files",
                "git_status": f"/projects/{project.id}/git/status",
            },
            "reporting": {
                "comment_author": f"agent.{task.node_name or 'dev'}",
                "comment_guidance": "After each run, post a comment with tests executed and screenshots captured.",
            },
        },
    }
    return context


def build_task_context_summary(task: Task, project: Project, db: Session) -> dict:
    """Return a concise context payload for prompting."""
    context = build_task_context_payload(task, project, db)
    task_info = context.get("task") or {}
    node_info = context.get("node") or {}
    objective_parts = [task_info.get("title"), task_info.get("description")]
    objective = "\n\n".join([part for part in objective_parts if part])
    git_info = context.get("git", {})
    last_comment_entry = (context.get("comments_recent") or [None])[0]
    max_files = 8
    last_commit_files = (git_info.get("last_commit_files") or [])[:max_files]
    working_changes = []
    for item in git_info.get("working_changes") or []:
        path = item.get("path")
        status = item.get("status")
        if not path or not status:
            continue
        # Skip workspace directories (runtime state) from git info
        if path.startswith("workspaces/"):
            continue
        working_changes.append(f"{status} {path}")
        if len(working_changes) >= max_files:
            break

    summary = {
        "task": {
            "id": task_info.get("id"),
            "project_id": task_info.get("project_id"),
            "parent_id": task_info.get("parent_id"),
            "node_id": task_info.get("node_id"),
            "node_name": task_info.get("node_name") or node_info.get("name"),
            "title": task_info.get("title"),
            "description": task_info.get("description"),
            "status": task_info.get("status"),
        },
        "project": {
            "id": project.id,
            "name": project.name,
            "workspace_path": project.workspace_path,
            "environment": project.environment,
        },
        "objective": objective,
        "acceptance_criteria": [
            {
                "id": item.get("id"),
                "description": item.get("description"),
                "passed": item.get("passed"),
            }
            for item in context.get("acceptance_criteria", [])
        ],
        "discovery": {
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
        },
        "recent_files": {
            "last_commit_summary": git_info.get("last_commit_summary"),
            "last_commit_files": last_commit_files,
            "working_changes": working_changes,
        },
        "last_comment": {
            "id": last_comment_entry.get("id") if last_comment_entry else None,
            "author": last_comment_entry.get("author") if last_comment_entry else None,
            "body": last_comment_entry.get("body") if last_comment_entry else None,
            "created_at": last_comment_entry.get("created_at") if last_comment_entry else None,
        } if last_comment_entry else None,
        "mcp": context.get("mcp"),
    }
    return summary
