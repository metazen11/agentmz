"""Database operations for observations.

Provides insert, update, delete, and query operations for the observations table.
Used by hooks (insert) and worker (update with classification/embedding).
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_session
from forge.agentmem.models import Observation, ObservationModel, ObservationType

logger = logging.getLogger(__name__)


def insert_observation(obs: Observation) -> int:
    """Insert a raw observation (embedding=NULL).

    Called by the observe.py hook after each tool call.
    Returns the observation ID.
    """
    with get_session() as session:
        model = obs.to_model()
        session.add(model)
        session.commit()
        session.refresh(model)
        return model.id


def get_pending_observations(limit: int = 100) -> List[Observation]:
    """Get observations that haven't been processed yet (embedding IS NULL).

    Called by the worker to find observations needing classification and embedding.
    """
    with get_session() as session:
        models = session.query(ObservationModel).filter(
            ObservationModel.embedding.is_(None)
        ).order_by(ObservationModel.id).limit(limit).all()

        return [Observation.from_model(m) for m in models]


def update_observation(
    obs_id: int,
    obs_type: ObservationType,
    title: str,
    tokens: int,
    embedding: Optional[List[float]] = None,
) -> None:
    """Update observation with classification and embedding.

    Called by the worker after classifying and embedding an observation.
    If embedding is None or empty, only classification fields are updated.
    """
    with get_session() as session:
        model = session.query(ObservationModel).filter(
            ObservationModel.id == obs_id
        ).first()

        if model:
            model.obs_type = obs_type.value
            model.title = title
            model.tokens = tokens
            # Only set embedding if we have a valid vector
            if embedding and len(embedding) > 0:
                model.embedding = embedding
            session.commit()


def delete_observation(obs_id: int) -> None:
    """Delete an observation (used for routine observations).

    Called by the worker when an observation is classified as routine.
    """
    with get_session() as session:
        session.query(ObservationModel).filter(
            ObservationModel.id == obs_id
        ).delete()
        session.commit()


def get_session_observations(session_id: str) -> List[Observation]:
    """Get all observations for a session.

    Used by classifier to analyze patterns within a session.
    """
    with get_session() as db_session:
        models = db_session.query(ObservationModel).filter(
            ObservationModel.session_id == session_id
        ).order_by(ObservationModel.timestamp).all()

        return [Observation.from_model(m) for m in models]


def count_pending() -> int:
    """Count observations pending processing."""
    with get_session() as session:
        return session.query(ObservationModel).filter(
            ObservationModel.embedding.is_(None)
        ).count()


def count_by_type() -> dict[str, int]:
    """Count observations by type."""
    with get_session() as session:
        result = session.execute(text("""
            SELECT obs_type, COUNT(*) as count
            FROM observations
            WHERE obs_type IS NOT NULL
            GROUP BY obs_type
        """))
        return {row[0]: row[1] for row in result}


def get_recent_tool_calls(
    session_id: str,
    tool: str,
    limit: int = 10,
) -> List[Observation]:
    """Get recent calls to a specific tool in a session.

    Used by classifier to detect repeated identical successes (routine).
    """
    with get_session() as db_session:
        models = db_session.query(ObservationModel).filter(
            ObservationModel.session_id == session_id,
            ObservationModel.tool == tool,
        ).order_by(ObservationModel.timestamp.desc()).limit(limit).all()

        return [Observation.from_model(m) for m in models]
