"""Data models for agent memory observations.

Observations represent tool attempts captured by hooks.
- Hook inserts raw data (embedding=NULL)
- Worker adds classification and embedding
- Retrieval uses cosine similarity for context injection
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base

# Conditional pgvector import
try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    Vector = None
    PGVECTOR_AVAILABLE = False


class ObservationType(str, Enum):
    """Classification of observation learning value."""
    GOLDEN = "golden"        # Hard-won success (multiple attempts)
    GOTCHA = "gotcha"        # Error that taught something
    DISCOVERY = "discovery"  # First use of tool/pattern
    ROUTINE = "routine"      # Repeated success, no learning (will be deleted)


class ObservationModel(Base):
    """SQLAlchemy model for observations table.

    Stores tool attempt observations for agent learning:
    - Raw data inserted by hook (embedding=NULL)
    - Classification and embedding added by worker
    - Retrieved via cosine similarity for context injection
    """
    __tablename__ = "observations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Context: where this observation happened
    project_id = Column(BigInteger, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    file_path = Column(Text, nullable=True)

    # External system references (Asana, Jira, GitHub, etc.)
    # Example: {"asana": {"task_id": "123"}, "github": {"pr": 456}}
    external_refs = Column(JSONB, nullable=True)

    # Raw tool data (inserted by hook)
    tool = Column(String(100), nullable=False)
    args_summary = Column(Text, nullable=True)  # Sanitized, truncated (~500 chars)
    output_summary = Column(Text, nullable=True)  # Truncated output (~500 chars)
    exit_code = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False)
    duration_ms = Column(Integer, nullable=True)

    # Classification (added by worker, NULL until processed)
    obs_type = Column(String(20), nullable=True)  # golden, gotcha, discovery
    title = Column(Text, nullable=True)  # Semantic summary (~10 words)
    tokens = Column(Integer, nullable=True)  # Estimated retrieval cost

    # Embedding (768-dim for nomic-embed-text, NULL until processed)
    embedding = Column(Vector(768) if PGVECTOR_AVAILABLE else Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    task = relationship("Task", foreign_keys=[task_id])

    def to_dict(self, include_embedding: bool = False) -> dict:
        """Convert to dictionary representation."""
        result = {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "file_path": self.file_path,
            "external_refs": self.external_refs,
            "tool": self.tool,
            "args_summary": self.args_summary,
            "output_summary": self.output_summary,
            "exit_code": self.exit_code,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "obs_type": self.obs_type,
            "title": self.title,
            "tokens": self.tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_embedding and self.embedding is not None:
            result["embedding"] = list(self.embedding) if hasattr(self.embedding, '__iter__') else None
        return result

    def to_index_entry(self) -> dict:
        """Compact representation for progressive disclosure index."""
        return {
            "id": self.id,
            "type": self.obs_type,
            "title": self.title,
            "tool": self.tool,
            "success": self.success,
            "tokens": self.tokens,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class Observation:
    """Dataclass for observation data transfer.

    Used for creating new observations and passing data between components.
    """
    session_id: str
    tool: str
    success: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Context
    project_id: int | None = None
    task_id: int | None = None
    file_path: str | None = None
    external_refs: dict[str, Any] | None = None

    # Tool data
    args_summary: str | None = None
    output_summary: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None

    # Classification (populated by worker)
    obs_type: ObservationType | None = None
    title: str | None = None
    tokens: int | None = None
    embedding: list[float] | None = None

    # Database ID (populated after insert)
    id: int | None = None

    def to_model(self) -> ObservationModel:
        """Convert to SQLAlchemy model for database insertion."""
        return ObservationModel(
            session_id=self.session_id,
            timestamp=self.timestamp,
            project_id=self.project_id,
            task_id=self.task_id,
            file_path=self.file_path,
            external_refs=self.external_refs,
            tool=self.tool,
            args_summary=self.args_summary,
            output_summary=self.output_summary,
            exit_code=self.exit_code,
            success=self.success,
            duration_ms=self.duration_ms,
            obs_type=self.obs_type.value if self.obs_type else None,
            title=self.title,
            tokens=self.tokens,
            embedding=self.embedding,
        )

    @classmethod
    def from_model(cls, model: ObservationModel) -> "Observation":
        """Create from SQLAlchemy model."""
        return cls(
            id=model.id,
            session_id=model.session_id,
            timestamp=model.timestamp,
            project_id=model.project_id,
            task_id=model.task_id,
            file_path=model.file_path,
            external_refs=model.external_refs,
            tool=model.tool,
            args_summary=model.args_summary,
            output_summary=model.output_summary,
            exit_code=model.exit_code,
            success=model.success,
            duration_ms=model.duration_ms,
            obs_type=ObservationType(model.obs_type) if model.obs_type else None,
            title=model.title,
            tokens=model.tokens,
            embedding=list(model.embedding) if model.embedding else None,
        )
