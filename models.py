"""SQLAlchemy models for v2 agentic system."""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Project(Base):
    """Project with workspace path and environment."""
    __tablename__ = "projects"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    workspace_path = Column(Text, nullable=False)
    environment = Column(String(20), default="local")  # local | staging | prod
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "workspace_path": self.workspace_path,
            "environment": self.environment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Task(Base):
    """Task with subtask support via parent_id."""
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False)
    parent_id = Column(BigInteger, ForeignKey("tasks.id"), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="backlog")  # backlog | in_progress | done | failed
    stage = Column(String(20), default="dev")  # dev | qa | review | complete
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], back_populates="children")
    children = relationship("Task", back_populates="parent", cascade="all, delete-orphan")

    def to_dict(self, include_children=False):
        result = {
            "id": self.id,
            "project_id": self.project_id,
            "parent_id": self.parent_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "stage": self.stage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_children:
            result["children"] = [child.to_dict(include_children=True) for child in self.children]
        return result
