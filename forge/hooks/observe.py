"""Post-hook that captures tool attempts as observations.

Inserts raw observations into the database with embedding=NULL.
Background worker will later classify and embed these observations.

This hook runs after every tool call and captures:
- Tool name and sanitized arguments
- Output summary (truncated)
- Success/failure status
- Session and context info
"""

import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Session ID persists for the process lifetime
# Can be overridden via FORGE_SESSION_ID environment variable
_SESSION_ID: str | None = None

# Track tool start times for duration calculation
_TOOL_START_TIMES: dict[str, float] = {}

# Sensitive keys to redact
SENSITIVE_KEYS = {"password", "token", "secret", "key", "api_key", "auth", "credential"}

# Max length for summaries
MAX_SUMMARY_LENGTH = 500


def _get_session_id() -> str:
    """Get or create session ID for this process."""
    global _SESSION_ID
    if _SESSION_ID is None:
        _SESSION_ID = os.environ.get(
            "FORGE_SESSION_ID",
            f"forge-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )
    return _SESSION_ID


def _sanitize_args(args: dict[str, Any]) -> str:
    """Sanitize and truncate args to summary string."""
    sanitized = {}
    for key, value in args.items():
        # Redact sensitive values
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str):
            # Truncate long strings
            if len(value) > 200:
                sanitized[key] = value[:200] + "..."
            else:
                sanitized[key] = value
        else:
            sanitized[key] = str(value)[:200]

    # Convert to summary string
    summary = str(sanitized)
    if len(summary) > MAX_SUMMARY_LENGTH:
        summary = summary[:MAX_SUMMARY_LENGTH] + "..."
    return summary


def _extract_output_summary(result: Any) -> str:
    """Extract a summary from the result."""
    if result is None:
        return ""

    if isinstance(result, dict):
        # Common patterns
        if "output" in result:
            output = str(result["output"])
        elif "result" in result:
            output = str(result["result"])
        elif "error" in result:
            output = f"Error: {result['error']}"
        elif "message" in result:
            output = str(result["message"])
        else:
            output = str(result)
    elif isinstance(result, str):
        output = result
    else:
        output = str(result)

    # Truncate
    if len(output) > MAX_SUMMARY_LENGTH:
        output = output[:MAX_SUMMARY_LENGTH] + "..."
    return output


def _is_success(result: Any) -> tuple[bool, int | None]:
    """Determine success status and exit code from result."""
    if result is None:
        return True, 0

    if isinstance(result, dict):
        # Check explicit success field
        if "success" in result:
            return bool(result["success"]), result.get("exit_code", 0 if result["success"] else 1)

        # Check exit_code
        if "exit_code" in result:
            code = result["exit_code"]
            return code == 0, code

        # Check for error field
        if "error" in result and result["error"]:
            return False, 1

        # Default to success
        return True, 0

    return result is not None, 0


def _get_context() -> dict[str, Any]:
    """Get context from environment variables."""
    context = {}

    # Project and task from env
    if project_id := os.environ.get("FORGE_PROJECT_ID"):
        try:
            context["project_id"] = int(project_id)
        except ValueError:
            pass

    if task_id := os.environ.get("FORGE_TASK_ID"):
        try:
            context["task_id"] = int(task_id)
        except ValueError:
            pass

    # Current file path if available
    if file_path := os.environ.get("FORGE_CURRENT_FILE"):
        context["file_path"] = file_path

    # External refs from env (JSON string)
    if external_refs := os.environ.get("FORGE_EXTERNAL_REFS"):
        try:
            import json
            context["external_refs"] = json.loads(external_refs)
        except (json.JSONDecodeError, ValueError):
            pass

    return context


def pre_tool(tool_name: str, **kwargs) -> None:
    """Record tool start time for duration tracking."""
    _TOOL_START_TIMES[tool_name] = time.time()


def post_tool(tool_name: str, args: dict, result: Any) -> None:
    """Capture tool attempt as observation in database.

    Inserts with embedding=NULL - background worker will process later.
    """
    # Calculate duration
    start_time = _TOOL_START_TIMES.pop(tool_name, None)
    duration_ms = None
    if start_time:
        duration_ms = int((time.time() - start_time) * 1000)

    # Extract success and exit code
    success, exit_code = _is_success(result)

    # Build observation
    try:
        from forge.agentmem.models import Observation
        from forge.agentmem.store import insert_observation

        context = _get_context()

        obs = Observation(
            session_id=_get_session_id(),
            tool=tool_name,
            args_summary=_sanitize_args(args or {}),
            output_summary=_extract_output_summary(result),
            exit_code=exit_code,
            success=success,
            duration_ms=duration_ms,
            project_id=context.get("project_id"),
            task_id=context.get("task_id"),
            file_path=context.get("file_path"),
            external_refs=context.get("external_refs"),
        )

        insert_observation(obs)

    except Exception as e:
        # Best effort - don't fail the tool call
        logger.debug(f"Failed to record observation: {e}")
