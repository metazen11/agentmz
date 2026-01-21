"""Routers for Project CRUD operations."""
import os
import subprocess
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Project

router = APIRouter()


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


from env_utils import resolve_workspace_path

@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@router.post("", response_model=ProjectResponse)
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


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
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


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"deleted": True}
