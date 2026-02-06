"""Post-hook that automatically generates embeddings for stored content.

When solutions, code snippets, or documentation are stored via ProjectMemory,
this hook calls the embedding API to generate vectors for semantic search.
"""
import json
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Tools that store content worth embedding
EMBEDDABLE_TOOLS = {"store_solution", "store_code", "store_knowledge", "memory_store"}

# Embedding API configuration
EMBEDDING_API_BASE = os.environ.get("EMBEDDING_API_BASE", "http://localhost:8002")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")


def post_tool(tool_name: str, args: dict, result: Any) -> None:
    """Generate and store embedding after content storage operations.

    Args:
        tool_name: Name of the tool that was executed
        args: Arguments passed to the tool
        result: Result returned by the tool
    """
    if tool_name not in EMBEDDABLE_TOOLS:
        return

    # Only process successful storage operations
    if not isinstance(result, dict) or not result.get("success"):
        return

    content = args.get("content", "")
    if not content or len(content) < 10:  # Skip trivial content
        return

    try:
        embedding = _generate_embedding(content)
        if embedding:
            # Store the embedding back via the result (hooks can modify results)
            result["embedding"] = embedding
            result["embedding_dimensions"] = len(embedding)
            logger.debug(f"Generated embedding ({len(embedding)} dims) for {tool_name}")
    except Exception as e:
        # Best effort - don't fail the tool call
        logger.warning(f"Failed to generate embedding: {e}")


def _generate_embedding(text: str, model: Optional[str] = None) -> Optional[list[float]]:
    """Call the embedding API to generate a vector.

    Args:
        text: Content to embed
        model: Embedding model to use (defaults to EMBEDDING_MODEL)

    Returns:
        Embedding vector as list of floats, or None on failure
    """
    model = model or EMBEDDING_MODEL
    url = f"{EMBEDDING_API_BASE}/api/embeddings"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json={"text": text, "model": model},
                timeout=30.0,
            )
            response.raise_for_status()

        data = response.json()
        if data.get("success") and data.get("embedding"):
            return data["embedding"]

        logger.warning(f"Embedding API returned: {data}")
        return None

    except httpx.TimeoutException:
        logger.warning("Embedding API timed out")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"Embedding API error {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Embedding API exception: {e}")
        return None


def generate_embedding_sync(text: str, model: Optional[str] = None) -> Optional[list[float]]:
    """Public API for generating embeddings synchronously.

    Useful for direct calls from ProjectMemory or other components.
    """
    return _generate_embedding(text, model)
