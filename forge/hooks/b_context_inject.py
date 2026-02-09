"""Pre-hook that injects relevant context from ProjectMemory before LLM calls.

This enables RAG (Retrieval Augmented Generation) by automatically searching
the knowledge base for relevant context and injecting it into the prompt.

Also provides failure hints: when a tool fails, the next LLM call gets
suggestions from past similar failures (gotchas) and solutions (golden patterns).
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

# Track recent failures for hint injection
_last_failure: dict[str, Any] | None = None


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

    Injects two types of context:
    1. Knowledge base context (from ProjectMemory)
    2. Failure hints (from agentmem observations, if previous tool failed)

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
        # Fetch knowledge base context
        kb_context = _fetch_relevant_context(prompt)

        # Fetch failure hints (if previous tool failed)
        failure_hints = _fetch_failure_hints()

        # Build enhanced prompt with both contexts
        if kb_context or failure_hints:
            enhanced_prompt = _build_enhanced_prompt_with_hints(
                prompt, kb_context, failure_hints
            )
            # Update args in place (hooks can modify args)
            if "prompt" in args:
                args["prompt"] = enhanced_prompt
            elif "message" in args:
                args["message"] = enhanced_prompt
            elif "query" in args:
                args["query"] = enhanced_prompt

            logger.debug(
                f"Injected context for {tool_name}: "
                f"kb={len(kb_context) if kb_context else 0} chars, "
                f"hints={'yes' if failure_hints else 'no'}"
            )

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


def _build_enhanced_prompt_with_hints(
    original_prompt: str,
    kb_context: Optional[str],
    failure_hints: Optional[str],
) -> str:
    """Combine knowledge base context and failure hints with original prompt.

    Args:
        original_prompt: User's original prompt
        kb_context: Context from knowledge base (may be None)
        failure_hints: Hints from past failures (may be None)

    Returns:
        Enhanced prompt with all contexts
    """
    parts = []

    # Add failure hints first (most relevant for immediate recovery)
    if failure_hints:
        parts.append(failure_hints)

    # Add knowledge base context
    if kb_context:
        parts.append("## Relevant Context from Project Knowledge\n")
        parts.append(kb_context)

    # Add separator and original prompt
    if parts:
        parts.append("\n---\n")

    parts.append("## User Request\n")
    parts.append(original_prompt)

    return "\n".join(parts)


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


# =============================================================================
# Failure Hint Injection (from agentmem observations)
# =============================================================================

def post_tool(tool_name: str, args: dict, result: Any) -> None:
    """Track tool failures for hint injection.

    When a tool fails, we store the failure info. The next LLM call
    will search for similar failures and inject hints.
    """
    global _last_failure

    # Check if this was a failure
    if _is_failure(result):
        _last_failure = {
            "tool": tool_name,
            "args": args,
            "result": result,
            "error_output": _extract_error_output(result),
        }
        logger.debug(f"Tracked failure for {tool_name}")
    else:
        # Clear on success - no hints needed
        _last_failure = None


def _is_failure(result: Any) -> bool:
    """Check if result indicates failure."""
    if result is None:
        return False
    if isinstance(result, dict):
        if result.get("success") is False:
            return True
        if result.get("exit_code", 0) != 0:
            return True
        if result.get("error"):
            return True
    return False


def _extract_error_output(result: Any) -> str:
    """Extract error message from result."""
    if isinstance(result, dict):
        if "error" in result:
            return str(result["error"])
        if "output" in result:
            return str(result["output"])[:500]
        if "message" in result:
            return str(result["message"])
    return str(result)[:500]


def _fetch_failure_hints() -> Optional[str]:
    """Fetch hints from agentmem for the last failure.

    Returns:
        Formatted hints string, or None if no hints found
    """
    global _last_failure

    if not _last_failure:
        return None

    try:
        from forge.agentmem.retrieval import get_hints_for_failure, format_hints_for_prompt

        hints = get_hints_for_failure(
            tool=_last_failure["tool"],
            error_output=_last_failure["error_output"],
            limit=3,
        )

        if hints:
            logger.debug(f"Found {len(hints)} hints for {_last_failure['tool']} failure")
            # Clear failure after fetching hints
            _last_failure = None
            return format_hints_for_prompt(hints)

    except ImportError:
        logger.debug("agentmem not available for failure hints")
    except Exception as e:
        logger.debug(f"Failed to fetch failure hints: {e}")

    return None
