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

    node_payload = task.node.to_dict() if task.node else None
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
