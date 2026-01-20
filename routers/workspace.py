"""Routers for File Browser and Git operations."""
import os
import re
import subprocess
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
from fastapi.responses import PlainTextResponse

from database import get_db
from models import Project
from env_utils import resolve_workspace_path

router = APIRouter()

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

def _validate_branch_name(branch: str) -> None:
    if not branch or not isinstance(branch, str):
        raise HTTPException(status_code=400, detail="branch required")
    if branch.startswith("-") or branch in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid branch name")
    if ".." in branch or "@" in branch or "~" in branch or "\\" in branch:
        raise HTTPException(status_code=400, detail="invalid branch name")
    if not re.match(r"^[A-Za-z0-9._/-]+$", branch):
        raise HTTPException(status_code=400, detail="invalid branch name")

@router.get("/projects/{project_id}/files")
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


@router.get("/projects/{project_id}/git/branches")
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


@router.get("/projects/{project_id}/git/status")
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


@router.post("/projects/{project_id}/git/remote")
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


@router.post("/projects/{project_id}/git/pull")
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


@router.post("/projects/{project_id}/git/push")
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


@router.post("/projects/{project_id}/git/init")
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


@router.post("/projects/{project_id}/git/config")
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


@router.post("/projects/{project_id}/git/checkout")
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


@router.get("/projects/{project_id}/file/{file_path:path}")
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
