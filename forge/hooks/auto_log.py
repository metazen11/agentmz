"""Post-hook that logs tool executions to ~/.forge/tool_history.jsonl."""
import json
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path.home() / ".forge" / "tool_history.jsonl"


def post_tool(tool_name: str, args: dict, result) -> None:
    """Log tool execution to JSONL file."""
    # Ensure directory exists
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Build log entry
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "args": _sanitize_args(args),
        "success": _is_success(result),
    }

    # Append to log file
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Best effort - don't fail the tool call


def _sanitize_args(args: dict) -> dict:
    """Remove potentially sensitive data from args."""
    sanitized = {}
    for key, value in args.items():
        if key in {"password", "token", "secret", "key", "api_key"}:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:500] + "...[truncated]"
        else:
            sanitized[key] = value
    return sanitized


def _is_success(result) -> bool:
    """Determine if result indicates success."""
    if isinstance(result, dict):
        return result.get("success", True)
    return result is not None
