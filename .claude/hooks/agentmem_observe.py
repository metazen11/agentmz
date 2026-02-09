#!/usr/bin/env python3
"""
Claude Code Hook: Agent Memory Observer

Captures tool attempts as observations for the agentmem system.
On failures, injects hints from similar past successes (golden patterns).

Exit codes:
  0 - Success (continue)
  Non-zero - Would block Claude (we avoid this)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def read_input():
    """Read JSON input from stdin."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return {}


def get_session_id():
    """Get or create a session ID."""
    # Claude Code sets some env vars we can use
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    if session_id:
        return f"claude-{session_id}"

    # Fall back to date-based ID
    return f"claude-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def extract_tool_info(input_data):
    """Extract tool name, args, and result from hook input."""
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", {})

    # Determine success
    success = True
    exit_code = 0

    if isinstance(tool_result, dict):
        if "error" in tool_result:
            success = False
            exit_code = 1
        elif "exit_code" in tool_result:
            exit_code = tool_result.get("exit_code", 0)
            success = exit_code == 0

    # Build args summary (sanitize sensitive info)
    args_summary = ""
    sensitive_keys = {"password", "token", "secret", "key", "api_key", "auth"}

    if tool_input:
        sanitized = {}
        for k, v in tool_input.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, str) and len(v) > 200:
                sanitized[k] = v[:200] + "..."
            else:
                sanitized[k] = v
        args_summary = str(sanitized)[:500]

    # Build output summary
    output_summary = ""
    if isinstance(tool_result, dict):
        if "error" in tool_result:
            output_summary = f"Error: {tool_result['error']}"[:500]
        elif "output" in tool_result:
            output_summary = str(tool_result["output"])[:500]
        elif "result" in tool_result:
            output_summary = str(tool_result["result"])[:500]
    elif isinstance(tool_result, str):
        output_summary = tool_result[:500]

    return {
        "tool": tool_name,
        "args_summary": args_summary,
        "output_summary": output_summary,
        "success": success,
        "exit_code": exit_code,
    }


def insert_observation(session_id, tool_info):
    """Insert observation into database."""
    try:
        from env_utils import load_env
        load_env()

        # Import models to register SQLAlchemy relationships
        import models  # noqa: F401

        from forge.agentmem.models import Observation
        from forge.agentmem.store import insert_observation as db_insert

        obs = Observation(
            session_id=session_id,
            tool=tool_info["tool"],
            args_summary=tool_info["args_summary"],
            output_summary=tool_info["output_summary"],
            success=tool_info["success"],
            exit_code=tool_info["exit_code"],
        )

        return db_insert(obs)
    except Exception as e:
        # Silently fail - don't block Claude
        return None


def get_failure_hints(tool_info):
    """Search for similar golden patterns when there's a failure."""
    if tool_info["success"]:
        return None

    try:
        from env_utils import load_env
        load_env()

        # Import models to register SQLAlchemy relationships
        import models  # noqa: F401

        from forge.agentmem.retrieval import search_similar, format_hints_for_prompt

        # Build query from failure context
        query = f"{tool_info['tool']}: {tool_info['output_summary']}"

        # Search for golden patterns (successful fixes)
        results = search_similar(
            query=query,
            limit=3,
            obs_types=["golden"],  # Only successful patterns
        )

        if results:
            return format_hints_for_prompt(results)

    except Exception:
        pass

    return None


def main():
    input_data = read_input()

    if not input_data:
        sys.exit(0)

    session_id = get_session_id()
    tool_info = extract_tool_info(input_data)

    # Skip tools we don't care about
    skip_tools = {"TodoRead", "TodoWrite"}
    if tool_info["tool"] in skip_tools:
        sys.exit(0)

    # Insert observation (async, don't wait)
    insert_observation(session_id, tool_info)

    # On failure, print hints from similar past successes
    hints = get_failure_hints(tool_info)
    if hints:
        print(hints)

    sys.exit(0)


if __name__ == "__main__":
    main()
