"""Routers for Task Node CRUD operations."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Task, TaskNode

router = APIRouter()

class NodeCreate(BaseModel):
    name: str
    agent_prompt: str


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    agent_prompt: Optional[str] = None


class NodeResponse(BaseModel):
    id: int
    name: str
    agent_prompt: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

def get_node_or_404(node_id: int, db: Session) -> TaskNode:
    node = db.query(TaskNode).filter(TaskNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


def get_default_node(db: Session) -> TaskNode:
    node = db.query(TaskNode).filter(TaskNode.name == "dev").first()
    if not node:
        raise HTTPException(status_code=404, detail="Default node 'dev' not found")
    return node


@router.get("/nodes", response_model=List[NodeResponse])
def list_nodes(db: Session = Depends(get_db)):
    return db.query(TaskNode).order_by(TaskNode.id.asc()).all()


@router.get("/nodes/{node_id}", response_model=NodeResponse)
def get_node(node_id: int, db: Session = Depends(get_db)):
    return get_node_or_404(node_id, db)


@router.post("/nodes", response_model=NodeResponse)
def create_node(node: NodeCreate, db: Session = Depends(get_db)):
    name = node.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Node name is required")
    existing = db.query(TaskNode).filter(TaskNode.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Node name already exists")
    db_node = TaskNode(name=name, agent_prompt=node.agent_prompt)
    db.add(db_node)
    db.commit()
    db.refresh(db_node)
    return db_node


@router.patch("/nodes/{node_id}", response_model=NodeResponse)
def update_node(node_id: int, update: NodeUpdate, db: Session = Depends(get_db)):
    node = get_node_or_404(node_id, db)
    if update.name is None and update.agent_prompt is None:
        raise HTTPException(status_code=400, detail="No updates provided")
    if update.name is not None:
        name = update.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Node name is required")
        existing = db.query(TaskNode).filter(TaskNode.name == name, TaskNode.id != node_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Node name already exists")
        node.name = name
    if update.agent_prompt is not None:
        node.agent_prompt = update.agent_prompt
    db.commit()
    db.refresh(node)
    return node


@router.delete("/nodes/{node_id}")
def delete_node(node_id: int, db: Session = Depends(get_db)):
    node = get_node_or_404(node_id, db)
    task_count = db.query(Task).filter(Task.node_id == node_id).count()
    if task_count > 0:
        raise HTTPException(status_code=400, detail="Node is in use by tasks")
    db.delete(node)
    db.commit()
    return {"deleted": True, "node_id": node_id}
