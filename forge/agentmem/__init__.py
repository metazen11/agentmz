"""Agent Memory System - Tool observation capture, classification, and retrieval.

Architecture:
1. Hook (observe.py) captures tool attempts → INSERT with embedding=NULL
2. Worker classifies observations and generates embeddings
3. Retrieval via cosine similarity for context injection on failures

Usage:
    from forge.agentmem import Observation, ObservationType
    from forge.agentmem.retrieval import search_similar
    from forge.agentmem.worker import process_pending
"""

from forge.agentmem.models import Observation, ObservationType

__all__ = ["Observation", "ObservationType"]
