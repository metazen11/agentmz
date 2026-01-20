"""SQLAlchemy models for v2 agentic system."""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, Boolean
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
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete-orphan")
    acceptance_criteria = relationship(
        "TaskAcceptanceCriteria",
        back_populates="task",
        cascade="all, delete-orphan",
    )

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


class TaskComment(Base):
    """Comment attached to a task."""
    __tablename__ = "task_comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    author = Column(String(255), default="human", nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    task = relationship("Task", back_populates="comments")
    attachments = relationship("TaskAttachment", back_populates="comment", passive_deletes=True)

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskAttachment(Base):
    """File attachment linked to a task and optionally a comment."""
    __tablename__ = "task_attachments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    comment_id = Column(BigInteger, ForeignKey("task_comments.id", ondelete="CASCADE"), nullable=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    storage_path = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    uploaded_by = Column(String(255), default="human", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    task = relationship("Task", back_populates="attachments")
    comment = relationship("TaskComment", back_populates="attachments")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "comment_id": self.comment_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "storage_path": self.storage_path,
            "url": self.url,
            "uploaded_by": self.uploaded_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TaskAcceptanceCriteria(Base):
    """Acceptance criteria attached to a task."""
    __tablename__ = "task_acceptance_criteria"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    passed = Column(Boolean, default=False, nullable=False)
    author = Column(String(255), default="user", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    task = relationship("Task", back_populates="acceptance_criteria")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "description": self.description,
            "passed": self.passed,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
