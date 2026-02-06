"""Pre-hook that injects relevant context from ProjectMemory before LLM calls.

This enables RAG (Retrieval Augmented Generation) by automatically searching
the knowledge base for relevant context and injecting it into the prompt.
"""
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Tools that send prompts to the LLM
LLM_TOOLS = {"chat", "generate", "ask_llm", "complete", "agent_run"}

# Context injection settings
MAX_CONTEXT_TOKENS = int(os.environ.get("RAG_MAX_CONTEXT_TOKENS", "2000"))
MIN_SIMILARITY_THRESHOLD = float(os.environ.get("RAG_MIN_SIMILARITY", "0.3"))

# Lazy import to avoid circular dependencies
_memory = None


def _get_memory():
    """Lazy load ProjectMemory to avoid import issues."""
    global _memory
    if _memory is None:
        try:
            from forge.memory import ProjectMemory
            project_id = int(os.environ.get("FORGE_PROJECT_ID", "1"))
            _memory = ProjectMemory(project_id=project_id)
        except Exception as e:
            logger.warning(f"Could not initialize ProjectMemory: {e}")
            return None
    return _memory


def pre_tool(tool_name: str, args: dict) -> bool:
    """Inject relevant context into LLM prompts.

    Args:
        tool_name: Name of the tool about to execute
        args: Arguments that will be passed to the tool (mutable)

    Returns:
        True to proceed with execution (always returns True)
    """
    if tool_name not in LLM_TOOLS:
        return True

    # Get the prompt/query from args
    prompt = args.get("prompt") or args.get("message") or args.get("query", "")
    if not prompt:
        return True

    try:
        context = _fetch_relevant_context(prompt)
        if context:
            # Inject context into the prompt
            enhanced_prompt = _build_enhanced_prompt(prompt, context)
            # Update args in place (hooks can modify args)
            if "prompt" in args:
                args["prompt"] = enhanced_prompt
            elif "message" in args:
                args["message"] = enhanced_prompt
            elif "query" in args:
                args["query"] = enhanced_prompt

            logger.debug(f"Injected {len(context)} chars of context for {tool_name}")

    except Exception as e:
        # Best effort - don't block the tool call
        logger.warning(f"Context injection failed: {e}")

    return True


def _fetch_relevant_context(query: str) -> Optional[str]:
    """Search ProjectMemory for relevant context.

    Args:
        query: The user's query/prompt

    Returns:
        Formatted context string, or None if nothing relevant found
    """
    memory = _get_memory()
    if memory is None:
        return None

    try:
        # Try to get embedding for semantic search
        embedding = _get_query_embedding(query)

        # Search the knowledge base
        context = memory.get_context(
            query=query,
            embedding=embedding,
            max_tokens=MAX_CONTEXT_TOKENS,
        )

        if context and len(context.strip()) > 20:
            return context
        return None

    except Exception as e:
        logger.debug(f"Context fetch failed: {e}")
        return None


def _get_query_embedding(query: str) -> Optional[list[float]]:
    """Generate embedding for the query (for semantic search).

    Args:
        query: Text to embed

    Returns:
        Embedding vector or None
    """
    try:
        from forge.hooks.auto_embed import generate_embedding_sync
        return generate_embedding_sync(query)
    except Exception:
        return None


def _build_enhanced_prompt(original_prompt: str, context: str) -> str:
    """Combine context with the original prompt.

    Args:
        original_prompt: User's original prompt
        context: Retrieved context from knowledge base

    Returns:
        Enhanced prompt with context prepended
    """
    return f"""## Relevant Context from Project Knowledge

{context}

---

## User Request

{original_prompt}"""


def inject_context(prompt: str, project_id: Optional[int] = None) -> str:
    """Public API for manually injecting context into a prompt.

    Useful for direct integration without going through the hook system.

    Args:
        prompt: The prompt to enhance
        project_id: Optional project ID (uses env default if not provided)

    Returns:
        Enhanced prompt with context, or original if no context found
    """
    if project_id:
        os.environ["FORGE_PROJECT_ID"] = str(project_id)
        global _memory
        _memory = None  # Reset to pick up new project ID

    context = _fetch_relevant_context(prompt)
    if context:
        return _build_enhanced_prompt(prompt, context)
    return prompt
