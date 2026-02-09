"""Retrieval via cosine similarity search.

Provides:
- search_similar(): Find observations similar to a query
- get_hints_for_failure(): Get suggestions when a tool fails
- get_index(): Compact list of recent observations

Used by context injection hook to provide hints on tool failures.
"""

import logging
from typing import List, Optional

from sqlalchemy import text

from database import get_session
from forge.agentmem.embedder import generate_embedding
from forge.agentmem.models import Observation, ObservationModel, ObservationType

logger = logging.getLogger(__name__)


def search_similar(
    query: str,
    limit: int = 5,
    obs_types: Optional[List[str]] = None,
    min_similarity: float = 0.3,
) -> List[dict]:
    """Search for observations similar to query.

    Args:
        query: Search query text
        limit: Maximum results
        obs_types: Filter by observation types (default: golden, gotcha)
        min_similarity: Minimum cosine similarity (0-1)

    Returns:
        List of observation dicts with similarity scores
    """
    # Default to valuable observation types
    if obs_types is None:
        obs_types = [ObservationType.GOLDEN.value, ObservationType.GOTCHA.value]

    # Generate embedding for query
    query_embedding = generate_embedding(query)
    if not query_embedding:
        logger.warning("Failed to generate query embedding")
        return []

    # Format embedding for PostgreSQL - inline in query to avoid cast issues
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    with get_session() as session:
        # Cosine similarity search
        # <=> is the cosine distance operator, we convert to similarity
        # Note: embedding is inlined because ::vector cast conflicts with SQLAlchemy param binding
        query = f"""
            SELECT
                id,
                session_id,
                tool,
                title,
                output_summary,
                obs_type,
                success,
                tokens,
                timestamp,
                1 - (embedding <=> '{embedding_str}'::vector) as similarity
            FROM observations
            WHERE embedding IS NOT NULL
              AND obs_type = ANY(:obs_types)
              AND 1 - (embedding <=> '{embedding_str}'::vector) >= :min_similarity
            ORDER BY embedding <=> '{embedding_str}'::vector
            LIMIT :limit
        """
        result = session.execute(
            text(query),
            {
                "obs_types": obs_types,
                "min_similarity": min_similarity,
                "limit": limit,
            }
        )

        observations = []
        for row in result:
            observations.append({
                "id": row.id,
                "session_id": row.session_id,
                "tool": row.tool,
                "title": row.title,
                "output_summary": row.output_summary,
                "obs_type": row.obs_type,
                "success": row.success,
                "tokens": row.tokens,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "similarity": float(row.similarity),
            })

        return observations


def get_hints_for_failure(
    tool: str,
    error_output: str,
    limit: int = 3,
) -> List[dict]:
    """Get hints for a tool failure based on past experience.

    Used by context injection to help agent recover from errors.

    Args:
        tool: The tool that failed
        error_output: The error message/output
        limit: Maximum hints to return

    Returns:
        List of relevant past observations with solutions
    """
    # Build query combining tool and error
    query = f"Tool: {tool}\nError: {error_output[:300]}"

    # Search for gotchas and golden patterns
    results = search_similar(
        query=query,
        limit=limit,
        obs_types=[ObservationType.GOTCHA.value, ObservationType.GOLDEN.value],
        min_similarity=0.4,
    )

    return results


def format_hints_for_prompt(hints: List[dict]) -> str:
    """Format hints for injection into prompt.

    Args:
        hints: List of observation dicts from search

    Returns:
        Formatted string to inject into prompt
    """
    if not hints:
        return ""

    lines = ["## Previous Similar Issues\n"]

    for hint in hints:
        obs_type = hint.get("obs_type", "")
        title = hint.get("title", "")
        output = hint.get("output_summary", "")

        # Truncate output for prompt
        if len(output) > 200:
            output = output[:200] + "..."

        type_label = "Fix" if obs_type == "golden" else "Issue"
        lines.append(f"- **{type_label}**: {title}")
        if output:
            lines.append(f"  Output: {output}")
        lines.append("")

    return "\n".join(lines)


def get_index(limit: int = 50) -> List[dict]:
    """Get compact index of recent observations.

    Progressive disclosure: return minimal info, agent can request details.

    Args:
        limit: Maximum observations

    Returns:
        List of compact observation dicts
    """
    with get_session() as session:
        models = session.query(ObservationModel).filter(
            ObservationModel.embedding.isnot(None),
            ObservationModel.obs_type.isnot(None),
        ).order_by(
            ObservationModel.timestamp.desc()
        ).limit(limit).all()

        return [m.to_index_entry() for m in models]


def get_observation_details(obs_ids: List[int]) -> List[dict]:
    """Get full details for specific observations.

    Args:
        obs_ids: List of observation IDs

    Returns:
        List of full observation dicts
    """
    with get_session() as session:
        models = session.query(ObservationModel).filter(
            ObservationModel.id.in_(obs_ids)
        ).all()

        return [m.to_dict() for m in models]
