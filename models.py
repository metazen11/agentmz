"""SQLAlchemy models for v2 agentic system."""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
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
    node_id = Column(BigInteger, ForeignKey("task_nodes.id"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="backlog")  # backlog | in_progress | done | failed
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], back_populates="children")
    children = relationship("Task", back_populates="parent", cascade="all, delete-orphan")
    node = relationship("TaskNode", back_populates="tasks")
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete-orphan")
    acceptance_criteria = relationship(
        "TaskAcceptanceCriteria",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    runs = relationship("TaskRun", back_populates="task", cascade="all, delete-orphan")

    def to_dict(self, include_children=False):
        result = {
            "id": self.id,
            "project_id": self.project_id,
            "parent_id": self.parent_id,
            "node_id": self.node_id,
            "node_name": self.node.name if self.node else None,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_children:
            result["children"] = [child.to_dict(include_children=True) for child in self.children]
        return result

    @property
    def node_name(self):
        return self.node.name if self.node else None


class TaskNode(Base):
    """Workflow node defining agent role and prompt."""
    __tablename__ = "task_nodes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    agent_prompt = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tasks = relationship("Task", back_populates="node")
    runs = relationship("TaskRun", back_populates="node")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "agent_prompt": self.agent_prompt,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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


class TaskRun(Base):
    """Agent run execution record for a task."""
    __tablename__ = "task_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    node_id = Column(BigInteger, ForeignKey("task_nodes.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="started", nullable=False)
    summary = Column(Text, nullable=True)
    tests_run = Column(JSONB, nullable=True)
    screenshots = Column(JSONB, nullable=True)
    tool_calls = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    task = relationship("Task", back_populates="runs")
    node = relationship("TaskNode", back_populates="runs")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "status": self.status,
            "summary": self.summary,
            "tests_run": self.tests_run,
            "screenshots": self.screenshots,
            "tool_calls": self.tool_calls,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ============================================================================
# Integration Models (External Task Providers)
# ============================================================================


class IntegrationProvider(Base):
    """Available external task providers (Asana, Jira, etc.)."""
    __tablename__ = "integration_providers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)  # 'asana', 'jira', etc.
    display_name = Column(String(100), nullable=False)  # 'Asana', 'Jira', etc.
    auth_type = Column(String(20), nullable=False)  # 'pat', 'oauth2', 'api_key'
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    credentials = relationship(
        "IntegrationCredential",
        back_populates="provider",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "auth_type": self.auth_type,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IntegrationCredential(Base):
    """Encrypted API credentials for external providers."""
    __tablename__ = "integration_credentials"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider_id = Column(
        BigInteger,
        ForeignKey("integration_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)  # User label: "My Asana Account"
    encrypted_token = Column(Text, nullable=False)  # Fernet-encrypted token
    is_valid = Column(Boolean, default=True, nullable=False)
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    provider = relationship("IntegrationProvider", back_populates="credentials")
    project_integrations = relationship(
        "ProjectIntegration",
        back_populates="credential",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_token=False):
        result = {
            "id": self.id,
            "provider_id": self.provider_id,
            "provider_name": self.provider.name if self.provider else None,
            "provider_display_name": self.provider.display_name if self.provider else None,
            "name": self.name,
            "is_valid": self.is_valid,
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        # Never expose encrypted_token in API responses
        return result


class ProjectIntegration(Base):
    """Links local Project to external project."""
    __tablename__ = "project_integrations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_id = Column(
        BigInteger,
        ForeignKey("integration_credentials.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_project_id = Column(String(255), nullable=False)  # Asana project gid
    external_project_name = Column(String(500), nullable=True)  # Cached name
    sync_direction = Column(String(20), default="import", nullable=False)  # 'import', 'export', 'bidirectional'
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project")
    credential = relationship("IntegrationCredential", back_populates="project_integrations")
    task_links = relationship(
        "TaskExternalLink",
        back_populates="integration",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "project_name": self.project.name if self.project else None,
            "credential_id": self.credential_id,
            "external_project_id": self.external_project_id,
            "external_project_name": self.external_project_name,
            "sync_direction": self.sync_direction,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskExternalLink(Base):
    """Maps local Task to external task ID."""
    __tablename__ = "task_external_links"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    integration_id = Column(
        BigInteger,
        ForeignKey("project_integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_task_id = Column(String(255), nullable=False)  # Asana task gid
    external_url = Column(Text, nullable=True)  # Direct link to task
    sync_status = Column(String(20), default="synced", nullable=False)  # 'synced', 'pending', 'conflict'
    sync_hash = Column(String(64), nullable=True)  # For change detection
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    task = relationship("Task")
    integration = relationship("ProjectIntegration", back_populates="task_links")

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "integration_id": self.integration_id,
            "external_task_id": self.external_task_id,
            "external_url": self.external_url,
            "sync_status": self.sync_status,
            "sync_hash": self.sync_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
