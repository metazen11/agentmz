#!/usr/bin/env python3
"""
Forge agent runner - wraps agent_cli.py logic for TUI and yolo modes.
"""
import json
import os
import sys
from typing import Any, Generator, Optional

# Add scripts dir to path for agent_cli imports
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import agent_cli functions
try:
    from agent_cli import (
        _build_client,
        _build_tools,
        _resolve_workspace as _agent_resolve_workspace,
        _run_loop,
        _check_ollama_service,
        _extract_tool_calls_from_text,
        ResponseError,
        SystemMessage,
        HumanMessage,
    )
except ImportError as e:
    raise ImportError(f"Failed to import agent_cli: {e}. Ensure scripts/agent_cli.py exists.")


def _resolve_workspace(workspace: str) -> str:
    """Resolve workspace path - supports absolute paths and workspace names."""
    if not workspace:
        return os.getcwd()
    # If it's an absolute path, use it directly
    if os.path.isabs(workspace):
        return workspace
    # If it exists relative to cwd, use it
    if os.path.isdir(workspace):
        return os.path.abspath(workspace)
    # Otherwise use the agent_cli resolver (workspaces/name)
    return _agent_resolve_workspace(workspace)


def _run_fallback_with_results(
    llm,
    tools,
    prompt: str,
    max_iters: int = 6,
) -> str:
    """
    Run text fallback mode and return formatted results.

    Returns a summary of executed tools and their results.
    Single iteration for simple queries, multi-turn for complex tasks.
    """
    tool_map = {t.name: t for t in tools}
    system_message = (
        "You are Forge. Execute tasks using JSON tool calls. "
        "Respond ONLY with JSON: {\"name\":\"tool_name\",\"arguments\":{...}}. "
        "Available: " + ", ".join(tool_map.keys())
    )

    response = llm.invoke([
        SystemMessage(content=system_message),
        HumanMessage(content=prompt),
    ])
    content = response.content or ""

    tool_calls = _extract_tool_calls_from_text(content)
    if not tool_calls:
        return content.strip() if content.strip() else "No actions taken."

    results = []
    for call in tool_calls:
        name = call.get("name")
        args = call.get("args") or {}

        # Normalize common argument name variations
        if "file_path" in args and "path" not in args:
            args["path"] = args.pop("file_path")
        if "file" in args and "path" not in args:
            args["path"] = args.pop("file")
        if "filename" in args and "path" not in args:
            args["path"] = args.pop("filename")

        tool_fn = tool_map.get(name)

        if not tool_fn:
            results.append(f"[{name}] Unknown tool")
            continue

        try:
            result = tool_fn.invoke(args)
            if isinstance(result, dict):
                if result.get("success"):
                    if "files" in result:
                        files = result["files"]
                        count = result.get("count", len(files))
                        results.append(f"Found {count} items:")
                        for f in files[:30]:
                            results.append(f"  {f}")
                        if count > 30:
                            results.append(f"  ... and {count - 30} more")
                    elif "content" in result:
                        path = result.get('path', 'file')
                        results.append(f"Contents of {path}:")
                        results.append(result['content'][:1000])
                    elif "path" in result:
                        results.append(f"Created: {result['path']} ({result.get('bytes', 0)} bytes)")
                    elif "matches" in result:
                        results.append(f"Found {result.get('count', 0)} matches:")
                        for m in result.get("matches", [])[:10]:
                            results.append(f"  {m.get('file')}:{m.get('line')}: {m.get('text', '')[:60]}")
                    elif "message" in result:
                        # respond tool - display the message directly
                        results.append(result["message"])
                    else:
                        results.append(f"[{name}] OK")
                else:
                    results.append(f"Error: {result.get('error')}")
            else:
                results.append(str(result))
        except Exception as exc:
            results.append(f"Error: {exc}")

    return "\n".join(results) if results else "No actions taken."


def run_once(
    prompt: str,
    workspace: str = "poc",
    model: str = "gemma3:4b",
    ollama_url: str = "http://localhost:11435",
    max_iters: int = 6,
    timeout: int = 120,
) -> str:
    """
    Run a single prompt through the agent (yolo mode).

    Args:
        prompt: The task prompt
        workspace: Workspace name or path
        model: Ollama model name
        ollama_url: Ollama API base URL
        max_iters: Maximum agent iterations
        timeout: Timeout per LLM call in seconds

    Returns:
        Agent response text with tool results
    """
    if not _check_ollama_service(ollama_url, timeout=5.0, verify=True):
        return f"Error: Ollama unreachable at {ollama_url}"

    try:
        client = _build_client(
            model=model,
            base_url=ollama_url,
            ssl_verify=True,
            temperature=0,
            seed=None,
            timeout=float(timeout),
        )
    except Exception as e:
        return f"Error: {e}"

    workspace_root = _resolve_workspace(workspace)
    tools = _build_tools(workspace_root)
    client_with_tools = client.bind_tools(tools, tool_choice="auto")

    fallback_parser = os.environ.get("AGENT_CLI_TOOL_FALLBACK", "1").lower() in {"1", "true", "yes"}

    try:
        result = _run_loop(
            client_with_tools,
            tools,
            prompt,
            max_iters=max_iters,
            fallback_parser=fallback_parser,
            invoke_timeout=float(timeout),
            invoke_retries=2,
            retry_backoff=5.0,
        )
        return result
    except Exception as e:
        if ResponseError is not None and isinstance(e, ResponseError) and "does not support tools" in str(e):
            # Use improved text fallback that shows results
            return _run_fallback_with_results(client, tools, prompt, max_iters=max_iters)
        return f"Error: {e}"


def run_streaming(
    prompt: str,
    workspace: str = "poc",
    model: str = "gemma3:4b",
    ollama_url: str = "http://localhost:11435",
    max_iters: int = 6,
    timeout: int = 120,
) -> Generator[dict[str, Any], None, None]:
    """
    Run a prompt with streaming output for TUI display.

    Yields dicts with type: status/chunk/tool_call/tool_result/done/error
    """
    yield {"type": "status", "message": f"Connecting to {model}..."}

    if not _check_ollama_service(ollama_url, timeout=5.0, verify=True):
        yield {"type": "error", "message": f"Ollama unreachable at {ollama_url}"}
        return

    yield {"type": "status", "message": "Building agent..."}

    try:
        client = _build_client(
            model=model,
            base_url=ollama_url,
            ssl_verify=True,
            temperature=0,
            seed=None,
            timeout=float(timeout),
        )
    except Exception as e:
        yield {"type": "error", "message": f"Client error: {e}"}
        return

    workspace_root = _resolve_workspace(workspace)
    tools = _build_tools(workspace_root)

    yield {"type": "status", "message": f"Running in {workspace}..."}

    # Try with native tools first, fall back to text mode
    try:
        client_with_tools = client.bind_tools(tools, tool_choice="auto")
        fallback_parser = os.environ.get("AGENT_CLI_TOOL_FALLBACK", "1").lower() in {"1", "true", "yes"}
        result = _run_loop(
            client_with_tools,
            tools,
            prompt,
            max_iters=max_iters,
            fallback_parser=fallback_parser,
            invoke_timeout=float(timeout),
            invoke_retries=2,
            retry_backoff=5.0,
        )
        yield {"type": "done", "content": result}
    except Exception as e:
        if ResponseError is not None and isinstance(e, ResponseError) and "does not support tools" in str(e):
            yield {"type": "status", "message": "Using text fallback..."}
            result = _run_fallback_with_results(client, tools, prompt, max_iters=max_iters)
            yield {"type": "done", "content": result}
        else:
            yield {"type": "error", "message": str(e)}
