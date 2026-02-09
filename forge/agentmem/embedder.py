"""Embedding generation via /api/embeddings endpoint.

Calls the local embedding API (proxies to Ollama nomic-embed-text).
Used by worker to generate embeddings for observations.
"""

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# Configuration from environment
EMBEDDING_API_BASE = os.environ.get("EMBEDDING_API_BASE", "http://localhost:8002")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_TIMEOUT = int(os.environ.get("EMBEDDING_TIMEOUT", "30"))

# Expected dimensions for nomic-embed-text
EXPECTED_DIMENSIONS = 768


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text via API.

    Args:
        text: The text to embed

    Returns:
        List of floats (768 dimensions for nomic-embed-text) or None on failure
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        return None

    url = f"{EMBEDDING_API_BASE}/api/embeddings"

    try:
        with httpx.Client(timeout=EMBEDDING_TIMEOUT) as client:
            response = client.post(
                url,
                json={
                    "model": EMBEDDING_MODEL,
                    "text": text.strip(),
                }
            )

            if response.status_code != 200:
                logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Handle different response formats
            if "embedding" in data:
                embedding = data["embedding"]
            elif "data" in data and len(data["data"]) > 0:
                # OpenAI-style response
                embedding = data["data"][0].get("embedding", [])
            else:
                logger.error(f"Unexpected embedding response format: {data.keys()}")
                return None

            # Validate dimensions
            if len(embedding) != EXPECTED_DIMENSIONS:
                logger.warning(
                    f"Unexpected embedding dimensions: {len(embedding)} (expected {EXPECTED_DIMENSIONS})"
                )

            return embedding

    except httpx.TimeoutException:
        logger.error(f"Embedding request timed out after {EMBEDDING_TIMEOUT}s")
        return None
    except httpx.RequestError as e:
        logger.error(f"Embedding request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating embedding: {e}")
        return None


def generate_embedding_for_observation(
    tool: str,
    title: str,
    output_summary: str,
) -> Optional[List[float]]:
    """Generate embedding optimized for observation search.

    Combines tool name, title, and output for semantic matching.
    """
    # Build text optimized for search
    parts = [f"Tool: {tool}"]
    if title:
        parts.append(f"Title: {title}")
    if output_summary:
        # Limit output to avoid overwhelming the embedding
        output_snippet = output_summary[:300] if len(output_summary) > 300 else output_summary
        parts.append(f"Output: {output_snippet}")

    text = "\n".join(parts)
    return generate_embedding(text)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars = 1 token)."""
    return len(text) // 4 + 1
