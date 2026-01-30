#!/usr/bin/env python3
"""
Minimal LangChain CLI runner for Ollama.

Defaults come from .env. Example:
  python scripts/agent_cli.py --prompt "List files in /workspaces/poc"
"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(value: Optional[str], fallback: int) -> int:
    if value is None or value == "":
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback


def _float_env(value: Optional[str], fallback: Optional[float]) -> Optional[float]:
    if value is None or value == "":
        return fallback
    try:
        return float(value)
    except ValueError:
        return fallback

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool
    try:
        from langchain.agents import create_agent as _create_agent
    except Exception:  # pragma: no cover - fallback for older versions
        _create_agent = None
    try:
        from langgraph.prebuilt import create_react_agent as _create_react_agent
    except Exception:  # pragma: no cover - fallback if langgraph not available
        _create_react_agent = None
except Exception:  # pragma: no cover - import guard
    ChatOllama = None
    tool = None
    _create_agent = None
    _create_react_agent = None
    BaseMessage = HumanMessage = SystemMessage = ToolMessage = object

try:
    import requests
    from requests.exceptions import RequestException
except ImportError:
    requests = None
    RequestException = Exception

SCRIPT_DIR = os.path.dirname(__file__)
CODING_PRINCIPLES_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, os.pardir, "coding_principles.md"))

try:
    from ollama._types import ResponseError
except Exception:
    ResponseError = None


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _debug_enabled() -> bool:
    return os.environ.get("AGENT_CLI_DEBUG", "").lower() in {"1", "true", "yes"} or \
        os.environ.get("LC_DEBUG", "").lower() in {"1", "true", "yes"}


def _debug_payload_enabled() -> bool:
    return os.environ.get("AGENT_CLI_DEBUG_PAYLOAD", "").lower() in {"1", "true", "yes"}


def _trace_enabled() -> bool:
    return os.environ.get("AGENT_CLI_TRACE", "").lower() in {"1", "true", "yes"}


def _serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    serialized = []
    for message in messages:
        entry = {
            "type": message.type,
            "content": message.content,
        }
        if getattr(message, "name", None):
            entry["name"] = message.name
        if isinstance(message, ToolMessage):
            entry["tool_call_id"] = message.tool_call_id
        serialized.append(entry)
    return serialized


def _tool_debug_summary(tools, include_schema: bool = False) -> list[dict]:
    summary = []
    for tool_item in tools:
        entry = {
            "name": getattr(tool_item, "name", ""),
            "description": getattr(tool_item, "description", ""),
        }
        if include_schema:
            schema = getattr(tool_item, "args_schema", None)
            if schema is not None:
                try:
                    entry["args_schema"] = schema.model_json_schema()
                except Exception:
                    entry["args_schema"] = str(schema)
        summary.append(entry)
    return summary


def _debug_log(payload: dict) -> None:
    print("[AGENT_CLI_DEBUG] payload")
    print(json.dumps(payload, indent=2))


def _trace_log(label: str, payload: dict) -> None:
    print(f"[AGENT_CLI_TRACE] {label}")
    print(json.dumps(payload, indent=2))


def _log_responses_enabled() -> bool:
    return os.environ.get("AGENT_CLI_LOG_RESPONSES", "").lower() in {"1", "true", "yes"}


def _get_log_dir() -> str:
    return os.environ.get("AGENT_CLI_LOG_DIR", "logs")


def _extract_token_usage(response) -> dict:
    """Extract token usage from Ollama response metadata."""
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    # LangChain ChatOllama puts Ollama stats in response_metadata
    meta = getattr(response, "response_metadata", {}) or {}
    if meta:
        usage["prompt_tokens"] = meta.get("prompt_eval_count", 0)
        usage["completion_tokens"] = meta.get("eval_count", 0)
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        # Additional Ollama stats
        usage["total_duration_ms"] = meta.get("total_duration", 0) // 1_000_000
        usage["eval_duration_ms"] = meta.get("eval_duration", 0) // 1_000_000
    return usage


def _truncate_tool_result(content: str, max_chars: int = 500) -> str:
    """Truncate long tool results to save context space."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + f"... [truncated, {len(content)} chars total]"


def _get_max_context_messages() -> int:
    """Get max messages to keep in context (0 = unlimited)."""
    return int(os.environ.get("AGENT_CLI_MAX_CONTEXT_MESSAGES", "0") or "0")


def _get_truncate_tool_results() -> int:
    """Get max chars for tool results (0 = no truncation)."""
    return int(os.environ.get("AGENT_CLI_TRUNCATE_TOOL_RESULTS", "500") or "500")


def _fresh_context_enabled() -> bool:
    """Check if fresh context mode is enabled (reset after successful tool)."""
    return os.environ.get("AGENT_CLI_FRESH_CONTEXT", "1").lower() in {"1", "true", "yes"}


def _is_task_complete(tool_name: str, result: Any) -> bool:
    """Check if a tool result indicates the task is complete."""
    # File operations that indicate completion
    completion_tools = {"write_file", "apply_patch", "delete_file", "move_file", "copy_file"}
    if tool_name not in completion_tools:
        return False

    # Check for success
    if isinstance(result, dict):
        return result.get("success", False)
    if isinstance(result, str):
        return "success" in result.lower() and "true" in result.lower()
    return False


def _log_response(
    label: str,
    model: str,
    prompt: str,
    response_content: str,
    tool_calls: list,
    iteration: int,
    extra: Optional[dict] = None,
    token_usage: Optional[dict] = None,
) -> Optional[str]:
    """
    Write LLM response to a timestamped JSON file for post-analysis.

    Returns the file path if written, None otherwise.
    """
    if not _log_responses_enabled():
        return None

    from datetime import datetime

    log_dir = _get_log_dir()
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # Sanitize model name for filename
    model_slug = re.sub(r"[^a-zA-Z0-9_-]", "-", model)
    filename = f"{timestamp}_{model_slug}_{label}.json"
    filepath = os.path.join(log_dir, filename)

    payload = {
        "timestamp": datetime.now().isoformat(),
        "label": label,
        "model": model,
        "iteration": iteration,
        "prompt": prompt,
        "response": {
            "content": response_content,
            "tool_calls": tool_calls,
        },
        "token_usage": token_usage or {},
    }
    if extra:
        payload["extra"] = extra

    try:
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] logged_response {filepath}")
        return filepath
    except Exception as e:
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] log_response_error {e}")
        return None


def _is_placeholder_content(content: str) -> bool:
    """Check if content is placeholder/template text that should be rejected."""
    if not content or not isinstance(content, str):
        return True
    stripped = content.strip()
    # Reject obvious placeholders
    placeholders = {"...", "…", "<content>", "[content]", "your code here", "TODO"}
    if stripped in placeholders or len(stripped) < 10:
        return True
    return False


def _extract_tool_calls_from_text(text: str) -> list[dict]:
    if not text:
        return []
    raw = text.strip()
    blocks = []
    fence_pattern = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
    for match in fence_pattern.findall(raw):
        blocks.append(match.strip())
    if not blocks:
        blocks = [raw]

    calls: list[dict] = []
    for payload in blocks:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            name = data.get("name")
            args = data.get("arguments") or data.get("args") or {}
            # Validate write_file/apply_patch have real content
            if name in ("write_file", "apply_patch"):
                content = args.get("content") or args.get("patch") or ""
                if _is_placeholder_content(content):
                    continue  # Skip invalid tool calls
            if name:
                calls.append({"name": name, "args": args})
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("name"):
                    item_args = item.get("arguments") or item.get("args") or {}
                    item_name = item.get("name")
                    if item_name in ("write_file", "apply_patch"):
                        content = item_args.get("content") or item_args.get("patch") or ""
                        if _is_placeholder_content(content):
                            continue
                    calls.append({"name": item_name, "args": item_args})
    return calls


def _resolve_defaults(env: Dict[str, str]) -> dict:
    model = env.get("AGENT_CLI_MODEL") or env.get("AGENT_MODEL") or "gemma3:4b"
    base_url = (
        env.get("AGENT_CLI_OLLAMA_BASE")
        or env.get("OLLAMA_API_BASE_LOCAL")
        or env.get("OLLAMA_API_BASE")
        or "http://localhost:11434"
    )
    workspace = env.get("AGENT_CLI_WORKSPACE") or env.get("DEFAULT_WORKSPACE") or "poc"
    project_name = env.get("AGENT_CLI_PROJECT_NAME", "")
    use_langgraph = _truthy(env.get("AGENT_CLI_USE_LANGGRAPH"))
    max_iters = _int_env(env.get("AGENT_CLI_MAX_ITERS"), 6)
    if env.get("AGENT_CLI_SSL_VERIFY") in {None, ""}:
        ssl_verify = True
    else:
        ssl_verify = _truthy(env.get("AGENT_CLI_SSL_VERIFY"))
    tool_choice = env.get("AGENT_CLI_TOOL_CHOICE", "").strip() or "auto"
    temperature = _float_env(env.get("AGENT_CLI_TEMPERATURE"), None)
    seed = _int_env(env.get("AGENT_CLI_SEED"), 0)
    if env.get("AGENT_CLI_SEED") in {None, ""}:
        seed = None
    timeout = _float_env(env.get("OLLAMA_TIMEOUT"), 60.0)
    invoke_timeout = _float_env(env.get("AGENT_CLI_INVOKE_TIMEOUT"), 120.0)
    invoke_retries = _int_env(env.get("AGENT_CLI_INVOKE_RETRIES"), 2)
    retry_backoff = _float_env(env.get("AGENT_CLI_RETRY_BACKOFF"), 5.0)
    warmup = _truthy(env.get("AGENT_CLI_WARMUP"))
    return {
        "model": model,
        "base_url": base_url,
        "workspace": workspace,
        "project_name": project_name,
        "use_langgraph": use_langgraph,
        "max_iters": max_iters,
        "ssl_verify": ssl_verify,
        "tool_choice": tool_choice,
        "temperature": temperature,
        "seed": seed,
        "timeout": timeout,
        "invoke_timeout": invoke_timeout,
        "invoke_retries": invoke_retries,
        "retry_backoff": retry_backoff,
        "warmup": warmup,
    }


def _build_client(model: str, base_url: str, ssl_verify: bool, temperature: float | None, seed: int | None, timeout: float | None):
    if ChatOllama is None:
        raise RuntimeError(
            "langchain-ollama is required. Install with: pip install langchain-ollama"
        )
    client_kwargs = {"verify": ssl_verify}
    if timeout:
        client_kwargs["timeout"] = timeout
    model_kwargs = {}
    if temperature is not None:
        model_kwargs["temperature"] = temperature
    if seed is not None:
        model_kwargs["seed"] = seed
    return ChatOllama(
        model=model,
        base_url=base_url,
        client_kwargs=client_kwargs,
        sync_client_kwargs=client_kwargs,
        async_client_kwargs=client_kwargs,
        **model_kwargs,
    )


def _apply_unified_patch(original: str, patch_text: str) -> str:
    if not patch_text:
        raise ValueError("Patch content required")

    lines = patch_text.splitlines()
    hunks = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("@@ "):
            hunks.append({"header": line, "lines": []})
            idx += 1
            while idx < len(lines) and not lines[idx].startswith("@@ "):
                hunks[-1]["lines"].append(lines[idx])
                idx += 1
            continue
        idx += 1

    if not hunks:
        raise ValueError("No hunks found in patch")

    original_lines = original.splitlines(keepends=True)
    result = []
    cursor = 0

    def _parse_header(header: str) -> tuple[int, int]:
        match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", header)
        if not match:
            raise ValueError(f"Invalid hunk header: {header}")
        return int(match.group(1)), int(match.group(2))

    def _lines_match(expected: str, actual: str) -> bool:
        if actual.endswith("\n"):
            actual_core = actual[:-1]
        else:
            actual_core = actual
        return expected == actual or expected == actual_core

    for hunk in hunks:
        orig_start, _ = _parse_header(hunk["header"])
        target_index = max(orig_start - 1, 0)
        if target_index < cursor or target_index > len(original_lines):
            raise ValueError("Patch hunk out of range")
        result.extend(original_lines[cursor:target_index])
        cursor = target_index

        for hunk_line in hunk["lines"]:
            if hunk_line.startswith("\\"):
                continue
            if not hunk_line:
                raise ValueError("Patch contains empty hunk line")
            marker = hunk_line[0]
            content = hunk_line[1:]
            if marker == " ":
                if cursor >= len(original_lines):
                    raise ValueError("Patch context mismatch: unexpected EOF")
                if not _lines_match(content, original_lines[cursor]):
                    raise ValueError("Patch context mismatch")
                result.append(original_lines[cursor])
                cursor += 1
            elif marker == "-":
                if cursor >= len(original_lines):
                    raise ValueError("Patch context mismatch: unexpected EOF")
                if not _lines_match(content, original_lines[cursor]):
                    raise ValueError("Patch context mismatch")
                cursor += 1
            elif marker == "+":
                result.append(content + "\n")
            else:
                raise ValueError(f"Unsupported patch line: {hunk_line}")

    result.extend(original_lines[cursor:])
    return "".join(result)


def _resolve_workspace(workspace: str) -> str:
    if not workspace:
        return os.path.join(os.getcwd(), "workspaces")
    if workspace.startswith("[%root%]"):
        root = os.environ.get("PROJECT_ROOT") or os.getcwd()
        return workspace.replace("[%root%]", root)
    cleaned = workspace.replace("\\", "/").strip().lstrip("/")
    if cleaned.startswith("workspaces/"):
        cleaned = cleaned[len("workspaces/"):]
    base = os.environ.get("WORKSPACES_DIR") or os.path.join(os.getcwd(), "workspaces")
    return os.path.join(base, cleaned)


def _safe_path(base: str, user_path: str) -> str:
    if not user_path:
        return base
    if user_path in {"/", "\\", "."}:
        return base
    if user_path.startswith("/workspaces/"):
        user_path = user_path[len("/workspaces/"):]
    if user_path.startswith("workspaces/"):
        user_path = user_path[len("workspaces/"):]
    base_norm = os.path.normpath(base)
    if os.path.isabs(user_path):
        joined = os.path.normpath(user_path)
    else:
        joined = os.path.normpath(os.path.join(base, user_path))
    if not joined.startswith(base_norm):
        raise ValueError("Path escapes workspace")
    return joined


def _build_tools(workspace_root: str):
    if tool is None:
        raise RuntimeError("langchain-core tools not available")

    @tool
    def list_files(path: str = ".") -> dict:
        """List files in the workspace directory."""
        if isinstance(path, str):
            normalized = path.replace("\\", "/")
            if normalized.startswith("/workspaces/") or normalized.startswith("workspaces/"):
                path = "."
            if normalized in {"/", ""}:
                path = "."
        target = _safe_path(workspace_root, path)
        if not os.path.isdir(target):
            return {"success": False, "error": f"Not a directory: {path}"}
        entries = sorted(os.listdir(target))
        result = {"success": True, "files": entries, "count": len(entries)}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] list_files {path} -> {len(entries)} entries")
        return result

    @tool
    def glob(pattern: str) -> dict:
        """Find files using a glob pattern in the workspace."""
        if not pattern:
            return {"success": False, "error": "pattern required"}
        import glob as glob_module

        base = _safe_path(workspace_root, ".")
        matches = glob_module.glob(os.path.join(base, pattern), recursive=True)
        rel_matches = [
            os.path.relpath(path, workspace_root)
            for path in matches
        ]
        result = {"success": True, "matches": sorted(rel_matches), "count": len(rel_matches)}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] glob {pattern} -> {result['count']} matches")
        return result

    @tool
    def read_file(path: str, start: int = 1, lines: int = 200) -> dict:
        """Read a file from the workspace."""
        target = _safe_path(workspace_root, path)
        if not os.path.isfile(target):
            return {"success": False, "error": f"Not a file: {path}"}
        start = max(1, int(start))
        lines = max(1, min(int(lines), 500))
        with open(target, "r", encoding="utf-8", errors="ignore") as handle:
            all_lines = handle.readlines()
        slice_lines = all_lines[start - 1:start - 1 + lines]
        result = {
            "success": True,
            "path": path,
            "start": start,
            "lines": len(slice_lines),
            "total_lines": len(all_lines),
            "content": "".join(slice_lines),
        }
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] read_file {path} -> {result['lines']} lines")
        return result

    @tool
    def write_file(path: str, content: str) -> dict:
        """Write a new file to the workspace (fails if it exists)."""
        if not path:
            return {"success": False, "error": "path required"}
        target = _safe_path(workspace_root, path)
        if os.path.exists(target):
            return {"success": False, "error": f"File already exists: {path}"}
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content or "")
        result = {"success": True, "path": path, "bytes": len(content or "")}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] write_file {path} -> {result['bytes']} bytes")
        return result

    @tool
    def apply_patch(path: str, patch: str) -> dict:
        """Apply a unified diff patch to an existing file."""
        if not path:
            return {"success": False, "error": "path required"}
        if not patch:
            return {"success": False, "error": "patch required"}
        target = _safe_path(workspace_root, path)
        if not os.path.isfile(target):
            return {"success": False, "error": f"Not a file: {path}"}
        with open(target, "r", encoding="utf-8", errors="ignore") as handle:
            original = handle.read()
        try:
            updated = _apply_unified_patch(original, patch)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(updated)
        result = {"success": True, "path": path, "bytes": len(updated)}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] apply_patch {path} -> {result['bytes']} bytes")
        return result

    @tool
    def mkdir(path: str, exist_ok: bool = True) -> dict:
        """Create a directory (and parents) inside the workspace."""
        if not path:
            return {"success": False, "error": "path required"}
        target = _safe_path(workspace_root, path)
        try:
            os.makedirs(target, exist_ok=bool(exist_ok))
        except OSError as exc:
            return {"success": False, "error": str(exc)}
        result = {"success": True, "path": path}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] mkdir {path}")
        return result

    @tool
    def delete_file(path: str, recursive: bool = False) -> dict:
        """Delete a file or directory. Use recursive=true for directories."""
        if not path:
            return {"success": False, "error": "path required"}
        target = _safe_path(workspace_root, path)
        if not os.path.exists(target):
            return {"success": False, "error": f"Path not found: {path}"}
        try:
            if os.path.isdir(target):
                if not recursive:
                    return {"success": False, "error": "Directory delete requires recursive=true"}
                import shutil
                shutil.rmtree(target)
            else:
                os.remove(target)
        except OSError as exc:
            return {"success": False, "error": str(exc)}
        result = {"success": True, "path": path}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] delete_file {path}")
        return result

    @tool
    def move_file(src: str, dst: str) -> dict:
        """Move/rename a file or directory within the workspace."""
        if not src or not dst:
            return {"success": False, "error": "src and dst required"}
        src_path = _safe_path(workspace_root, src)
        dst_path = _safe_path(workspace_root, dst)
        if not os.path.exists(src_path):
            return {"success": False, "error": f"Source not found: {src}"}
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        try:
            import shutil
            shutil.move(src_path, dst_path)
        except OSError as exc:
            return {"success": False, "error": str(exc)}
        result = {"success": True, "src": src, "dst": dst}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] move_file {src} -> {dst}")
        return result

    @tool
    def copy_file(src: str, dst: str) -> dict:
        """Copy a file or directory within the workspace."""
        if not src or not dst:
            return {"success": False, "error": "src and dst required"}
        src_path = _safe_path(workspace_root, src)
        dst_path = _safe_path(workspace_root, dst)
        if not os.path.exists(src_path):
            return {"success": False, "error": f"Source not found: {src}"}
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        try:
            import shutil
            if os.path.isdir(src_path):
                if os.path.exists(dst_path):
                    return {"success": False, "error": f"Destination exists: {dst}"}
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)
        except OSError as exc:
            return {"success": False, "error": str(exc)}
        result = {"success": True, "src": src, "dst": dst}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] copy_file {src} -> {dst}")
        return result

    @tool
    def stat_path(path: str) -> dict:
        """Return file metadata (size, type, mtime)."""
        if not path:
            return {"success": False, "error": "path required"}
        target = _safe_path(workspace_root, path)
        if not os.path.exists(target):
            return {"success": False, "error": f"Path not found: {path}"}
        info = os.stat(target)
        result = {
            "success": True,
            "path": path,
            "size": info.st_size,
            "mtime": info.st_mtime,
            "is_dir": os.path.isdir(target),
            "is_file": os.path.isfile(target),
        }
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] stat_path {path}")
        return result

    @tool
    def list_tree(path: str = ".", max_depth: int = 2, max_files: int = 200) -> dict:
        """List files in a tree view up to a depth and limit."""
        base = _safe_path(workspace_root, path)
        if not os.path.isdir(base):
            return {"success": False, "error": f"Not a directory: {path}"}
        max_depth = max(0, int(max_depth))
        max_files = max(1, min(int(max_files), 2000))
        files = []
        base_depth = base.rstrip(os.sep).count(os.sep)
        for root, dirs, filenames in os.walk(base):
            depth = root.count(os.sep) - base_depth
            if depth > max_depth:
                dirs[:] = []
                continue
            rel_root = os.path.relpath(root, workspace_root)
            for name in sorted(filenames):
                rel_path = os.path.join(rel_root, name)
                files.append(rel_path.replace("\\", "/"))
                if len(files) >= max_files:
                    result = {"success": True, "files": files, "count": len(files), "truncated": True}
                    if _debug_enabled():
                        print(f"[AGENT_CLI_DEBUG] list_tree {path} -> {result['count']} files (truncated)")
                    return result
        result = {"success": True, "files": files, "count": len(files), "truncated": False}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] list_tree {path} -> {result['count']} files")
        return result

    @tool
    def grep(pattern: str, path: str = ".", glob_pattern: str = "*") -> dict:
        """Search for a regex pattern in workspace files."""
        import re
        from fnmatch import fnmatch

        base = _safe_path(workspace_root, path)
        if not os.path.isdir(base):
            return {"success": False, "error": f"Not a directory: {path}"}
        regex = re.compile(pattern)
        matches = []
        for root, _, files in os.walk(base):
            for file_name in files:
                if not fnmatch(file_name, glob_pattern):
                    continue
                file_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(file_path, workspace_root)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                        for idx, line in enumerate(handle, start=1):
                            if regex.search(line):
                                matches.append({"file": rel_path, "line": idx, "text": line.strip()})
                except OSError:
                    continue
        result = {"success": True, "count": len(matches), "matches": matches}
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] grep {pattern} -> {result['count']} matches")
        return result

    @tool
    def run_command(command: str) -> dict:
        """Run a safe shell command in the workspace."""
        import shlex
        import subprocess

        if not command or not isinstance(command, str):
            return {"success": False, "error": "command required"}
        parts = shlex.split(command)
        if not parts:
            return {"success": False, "error": "command required"}
        allowed = {"ls", "dir", "pwd", "cat", "type"}
        if parts[0] not in allowed:
            return {"success": False, "error": f"command not allowed: {parts[0]}"}

        if os.name == "nt":
            cmd = ["cmd.exe", "/c", command]
        else:
            cmd = ["bash", "-lc", command]

        result = subprocess.run(
            cmd,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        result = {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] run_command {command} -> {result['returncode']}")
        return result

    @tool
    def respond(message: str) -> dict:
        """Send a text response to the user. Use this for questions, explanations, or when no file operation is needed."""
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] respond: {message[:100]}...")
        return {"success": True, "message": message}

    return [
        list_files,
        glob,
        read_file,
        write_file,
        apply_patch,
        mkdir,
        delete_file,
        move_file,
        copy_file,
        stat_path,
        list_tree,
        grep,
        run_command,
        respond,
    ]


def _run_tool_fallback(
    llm,
    tools,
    messages: list[BaseMessage],
    max_iters: int,
    fallback_parser: bool,
    invoke_timeout: float = 120.0,
    invoke_retries: int = 2,
    retry_backoff: float = 5.0,
    original_prompt: str = "",
) -> str:
    debug = _debug_enabled()
    debug_payload = _debug_payload_enabled()
    trace = _trace_enabled()
    log_responses = _log_responses_enabled()
    tool_map = {t.name: t for t in tools}
    model_name = getattr(llm, "model", "unknown")

    for iteration in range(max_iters):
        if debug_payload:
            payload = {
                "model": model_name,
                "base_url": getattr(llm, "base_url", ""),
                "messages": _serialize_messages(messages),
                "tools": _tool_debug_summary(tools, include_schema=True),
            }
            _debug_log(payload)
        if trace:
            _trace_log("request", {
                "model": model_name,
                "base_url": getattr(llm, "base_url", ""),
                "messages": _serialize_messages(messages),
                "tools": _tool_debug_summary(tools, include_schema=False),
            })
        try:
            response = _invoke_with_retry(
                llm, messages, invoke_timeout,
                max_retries=invoke_retries, backoff=retry_backoff
            )
        except concurrent.futures.TimeoutError as exc:
            if debug:
                print(f"[AGENT_CLI_DEBUG] invoke_timeout {invoke_timeout}s after {invoke_retries} retries")
            raise RuntimeError(f"LLM invoke timed out after {invoke_timeout}s (retries exhausted)") from exc
        except Exception as exc:
            if requests is not None and isinstance(exc, RequestException):
                print("[AGENT_CLI_DEBUG] request_exception", exc)
            raise
        tool_calls = getattr(response, "tool_calls", None) or []

        # Extract and log token usage
        token_usage = _extract_token_usage(response)
        if token_usage.get("total_tokens", 0) > 0:
            print(f"[TOKENS] prompt={token_usage['prompt_tokens']} completion={token_usage['completion_tokens']} total={token_usage['total_tokens']}")

        if trace:
            _trace_log("response", {
                "content": response.content,
                "tool_calls": tool_calls,
                "token_usage": token_usage,
            })

        # Log response to file for post-analysis
        if log_responses:
            _log_response(
                label="response",
                model=model_name,
                prompt=original_prompt,
                response_content=response.content or "",
                tool_calls=tool_calls,
                iteration=iteration,
                token_usage=token_usage,
            )

        if debug and tool_calls:
            print(f"[LC] tool_calls: {tool_calls}")
        if not tool_calls and fallback_parser:
            parsed = _extract_tool_calls_from_text(response.content or "")
            if parsed:
                tool_calls = parsed
                if debug:
                    print(f"[AGENT_CLI_DEBUG] parsed_tool_calls: {tool_calls}")
            elif debug and response.content and "{" in response.content:
                print("[AGENT_CLI_DEBUG] fallback_parser rejected (placeholder content or invalid JSON)")
        if not tool_calls:
            if debug:
                print("[AGENT_CLI_DEBUG] final_response")
                print(response.content or "")
            return response.content or ""

        # Get truncation setting
        truncate_limit = _get_truncate_tool_results()
        fresh_context = _fresh_context_enabled()
        task_completed = False

        for call in tool_calls:
            name = call.get("name")
            args = call.get("args") or {}
            tool_fn = tool_map.get(name)
            if not tool_fn:
                messages.append(ToolMessage(content=f"Unknown tool: {name}", tool_call_id=name or "tool"))
                continue
            try:
                result = tool_fn.invoke(args)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}

            # Check if task is complete (successful file write, etc.)
            if _is_task_complete(name, result):
                task_completed = True
                if debug:
                    print(f"[AGENT_CLI_DEBUG] task_complete tool={name}")

            # Truncate long tool results to save context space
            result_str = str(result)
            if truncate_limit > 0:
                result_str = _truncate_tool_result(result_str, truncate_limit)

            messages.append(ToolMessage(content=result_str, tool_call_id=name or "tool"))

        # Fresh context mode: if task completed, return early instead of continuing loop
        if fresh_context and task_completed:
            summary = f"Task completed successfully. Last action: {name}"
            if debug:
                print(f"[AGENT_CLI_DEBUG] fresh_context_exit: {summary}")
            return summary

    return "Max iterations reached without final response."


def _run_text_fallback(
    llm,
    tools,
    prompt: str,
    max_iters: int,
) -> str:
    debug = _debug_enabled()
    trace = _trace_enabled()
    if debug:
        print("[AGENT_CLI_DEBUG] text_fallback_start")
    tool_map = {t.name: t for t in tools}
    system_message = (
        "Tools are unavailable in this environment. "
        "Respond only by emitting JSON tool calls with `name` and `arguments`, "
        "e.g. {\"name\":\"write_file\",\"arguments\":{\"path\":\"hello-world.html\",\"content\":\"<html>...</html>\"}}. "
        "Do not add prose outside the JSON payload. "
        "We will execute those commands locally on your behalf."
    )
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=prompt),
    ]
    if trace:
        _trace_log("fallback_request", {
            "model": getattr(llm, "model", ""),
            "base_url": getattr(llm, "base_url", ""),
            "messages": _serialize_messages(messages),
        })
    response = llm.invoke(messages)
    content = response.content or ""
    if trace:
        _trace_log("fallback_response", {
            "content": content,
        })
    tool_calls = _extract_tool_calls_from_text(content)
    if not tool_calls:
        return content
    for call in tool_calls:
        name = call.get("name")
        args = call.get("args") or {}
        tool_fn = tool_map.get(name)
        if not tool_fn:
            if debug:
                print(f"[AGENT_CLI_DEBUG] fallback_unknown_tool: {name}")
            continue
        try:
            result = tool_fn.invoke(args)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        if debug:
            print(f"[AGENT_CLI_DEBUG] fallback_tool {name} -> {result}")
    return content


def _trigger_ollama_heal() -> bool:
    heal_url = os.environ.get("OLLAMA_HEAL_URL")
    if not heal_url or requests is None:
        return False
    try:
        resp = requests.post(heal_url, timeout=5)
        if resp.status_code < 400:
            wait = float(os.environ.get("OLLAMA_HEAL_WAIT_SECS", "10"))
            time.sleep(wait)
            return True
    except RequestException as exc:
        print("[AGENT_CLI_DEBUG] ollama_heal_failed", exc)
    return False


def _check_ollama_service(base_url: str, timeout: float | None, verify: bool) -> bool:
    if requests is None:
        return True
    candidates = ["", "api/health", "api/models", "api/system"]
    for attempt in range(2):
        for suffix in candidates:
            target = base_url.rstrip("/")
            if suffix:
                target = f"{target}/{suffix.lstrip('/')}"
            try:
                resp = requests.get(target, timeout=timeout or 5, verify=verify)
                if resp.status_code < 500:
                    return True
            except RequestException:
                continue
        if attempt == 0 and _trigger_ollama_heal():
            continue
        break
    return False


def _invoke_with_timeout(llm, messages, timeout: float):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, messages)
        return future.result(timeout=timeout)


def _spinner_enabled() -> bool:
    """Check if spinner/progress indicator is enabled."""
    # Disabled by default; enable with AGENT_CLI_SPINNER=1
    return os.environ.get("AGENT_CLI_SPINNER", "1").lower() in {"1", "true", "yes"}


def _invoke_with_retry(
    llm, messages, timeout: float, max_retries: int = 2, backoff: float = 5.0
):
    """Invoke LLM with timeout and exponential backoff retry on timeout errors.

    After all retries are exhausted, attempts to heal Ollama via the main API
    and tries one final time.
    """
    debug = _debug_enabled()
    show_spinner = _spinner_enabled()
    model_name = getattr(llm, "model", "LLM")
    last_exc = None
    healed = False

    for attempt in range(max_retries + 1):
        if show_spinner:
            print(f"[WAITING] {model_name} responding...", end="", flush=True)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(llm.invoke, messages)
                start_time = time.time()
                while True:
                    try:
                        result = future.result(timeout=5.0)  # Check every 5s
                        if show_spinner:
                            elapsed = time.time() - start_time
                            print(f" done ({elapsed:.1f}s)")
                        return result
                    except concurrent.futures.TimeoutError:
                        elapsed = time.time() - start_time
                        if elapsed >= timeout:
                            if show_spinner:
                                print(f" timeout after {elapsed:.1f}s")
                            raise
                        if show_spinner:
                            print(f" {elapsed:.0f}s...", end="", flush=True)
        except concurrent.futures.TimeoutError as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = backoff * (2 ** attempt)
                if debug:
                    print(f"[AGENT_CLI_DEBUG] timeout_retry attempt={attempt+1}/{max_retries} wait={wait}s")
                time.sleep(wait)
            else:
                if debug:
                    print(f"[AGENT_CLI_DEBUG] timeout_exhausted retries={max_retries} timeout={timeout}s")

    # All retries exhausted - try to heal Ollama and attempt one final time
    if not healed:
        print("[AGENT_CLI] Retries exhausted, attempting to heal Ollama...")
        if _trigger_ollama_heal():
            healed = True
            print("[AGENT_CLI] Ollama healed, trying one more time...")
            if show_spinner:
                print(f"[WAITING] {model_name} responding (post-heal)...", end="", flush=True)
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(llm.invoke, messages)
                    start_time = time.time()
                    while True:
                        try:
                            result = future.result(timeout=5.0)
                            if show_spinner:
                                elapsed = time.time() - start_time
                                print(f" done ({elapsed:.1f}s)")
                            return result
                        except concurrent.futures.TimeoutError:
                            elapsed = time.time() - start_time
                            if elapsed >= timeout:
                                if show_spinner:
                                    print(f" timeout after {elapsed:.1f}s (post-heal)")
                                raise
                            if show_spinner:
                                print(f" {elapsed:.0f}s...", end="", flush=True)
            except concurrent.futures.TimeoutError as exc:
                last_exc = exc
                if debug:
                    print("[AGENT_CLI_DEBUG] timeout_after_heal")
        else:
            print("[AGENT_CLI] Ollama heal not available or failed")

    raise last_exc


def _warmup_ollama(base_url: str, model: str, timeout: float, verify: bool) -> bool:
    """Send a minimal request to warm up the Ollama connection and model loading."""
    if requests is None:
        return True
    debug = _debug_enabled()
    try:
        target = f"{base_url.rstrip('/')}/api/generate"
        payload = {"model": model, "prompt": "hi", "stream": False}
        resp = requests.post(target, json=payload, timeout=timeout, verify=verify)
        if debug:
            print(f"[AGENT_CLI_DEBUG] warmup status={resp.status_code}")
        return resp.status_code < 500
    except RequestException as exc:
        if debug:
            print(f"[AGENT_CLI_DEBUG] warmup_failed {exc}")
        return False


def _load_coding_principles_text() -> str:
    try:
        with open(CODING_PRINCIPLES_PATH, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
            return content if content else "(coding principles file is empty)"
    except OSError:
        return "(coding principles document unavailable)"


def _coding_principles_message() -> str:
    principles = _load_coding_principles_text()
    return (
        "You are Forge. Think step-by-step: (1) understand the task, (2) plan your approach, "
        "(3) execute one tool at a time. Keep responses minimal - output tool calls, not prose. "
        f"Principles:\n{principles}"
    )


def _run_loop(
    llm,
    tools,
    prompt: str,
    max_iters: int = 6,
    fallback_parser: bool = False,
    invoke_timeout: float = 120.0,
    invoke_retries: int = 2,
    retry_backoff: float = 5.0,
) -> str:
    debug = _debug_enabled()
    system_messages = [
        SystemMessage(content=_coding_principles_message()),
        SystemMessage(content=(
            "Use tools for all interactions: read_file to read, write_file to create, apply_patch to edit, "
            "respond to answer questions or explain things. Always use a tool - never output bare text."
        )),
    ]
    messages = system_messages + [HumanMessage(content=prompt)]
    if debug:
        print("[AGENT_CLI_DEBUG] starting_tool_loop")
    return _run_tool_fallback(
        llm, tools, messages,
        max_iters=max_iters,
        fallback_parser=fallback_parser,
        invoke_timeout=invoke_timeout,
        invoke_retries=invoke_retries,
        retry_backoff=retry_backoff,
        original_prompt=prompt,
    )


def _retention_cleanup(conn_string: str, days: int) -> None:
    if days <= 0:
        return
    try:
        import psycopg
    except Exception:
        return
    query = """
        DELETE FROM checkpoints
        WHERE metadata ? 'created_at'
          AND (metadata->>'created_at')::timestamptz < (now() - (%s || ' days')::interval)
    """
    try:
        with psycopg.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (days,))
            conn.commit()
    except Exception:
        return


def main() -> int:
    _load_env()
    defaults = _resolve_defaults(os.environ)
    parser = argparse.ArgumentParser(description="Run a LangChain chat call against Ollama")
    parser.add_argument("--prompt", help="Prompt to send to the model")
    parser.add_argument("--prompt-file", help="Path to a file containing the prompt")
    parser.add_argument("--model", default=defaults["model"])
    parser.add_argument("--ollama", default=defaults["base_url"])
    parser.add_argument("--workspace", default=defaults["workspace"])
    parser.add_argument("--project-name", default=defaults["project_name"])
    parser.add_argument(
        "--use-langgraph",
        action="store_true",
        default=defaults["use_langgraph"],
        help="Use LangGraph with persistence",
    )
    parser.add_argument("--max-iters", type=int, default=defaults["max_iters"])
    parser.add_argument(
        "--invoke-timeout",
        type=float,
        default=defaults["invoke_timeout"],
        help="Timeout in seconds for each LLM invoke (default: 120)",
    )
    parser.add_argument(
        "--invoke-retries",
        type=int,
        default=defaults["invoke_retries"],
        help="Number of retries on timeout (default: 2)",
    )
    args = parser.parse_args()

    model = args.model
    base_url = args.ollama.rstrip("/")
    prompt = args.prompt or ""
    if args.prompt_file:
        try:
            with open(args.prompt_file, "r", encoding="utf-8") as handle:
                prompt = handle.read()
        except OSError as exc:
            print(f"Failed to read prompt file: {exc}")
            return 1
    if not prompt:
        print("Prompt is required (use --prompt or --prompt-file)")
        return 1

    if not _check_ollama_service(base_url, defaults["timeout"], defaults["ssl_verify"]):
        print(f"Ollama service unreachable at {base_url}; verify the server is running.")
        return 1

    if defaults["warmup"]:
        if _debug_enabled():
            print(f"[AGENT_CLI_DEBUG] warming_up model={model}")
        _warmup_ollama(base_url, model, defaults["timeout"], defaults["ssl_verify"])

    # Use invoke_timeout for HTTP client so both timeouts are synced
    http_timeout = args.invoke_timeout or defaults["invoke_timeout"]
    try:
        client = _build_client(
        model,
        base_url,
        defaults["ssl_verify"],
        defaults["temperature"],
        defaults["seed"],
        http_timeout,
    )
    except RuntimeError as exc:
        print(str(exc))
        return 1

    workspace_root = _resolve_workspace(args.workspace)
    tools = _build_tools(workspace_root)
    client = client.bind_tools(tools, tool_choice=defaults["tool_choice"])

    fallback_parser = os.environ.get("AGENT_CLI_TOOL_FALLBACK", "").lower() in {"1", "true", "yes"}

    if args.use_langgraph:
        if _create_agent is None and _create_react_agent is None:
            print("langgraph is required. Install with: pip install langgraph")
            return 1
        thread_id = f"project:{args.project_name or args.workspace}"
        conn_string = os.environ.get("DATABASE_URL", "")
        if not conn_string:
            print("DATABASE_URL is required for persistent memory")
            return 1
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except Exception as exc:
            print(f"PostgresSaver unavailable: {exc}")
            return 1
        retention_days = int(os.environ.get("LC_RETENTION_DAYS", "0") or "0")
        _retention_cleanup(conn_string, retention_days)

        with PostgresSaver.from_conn_string(conn_string) as checkpointer:
            checkpointer.setup()
            if _create_agent is not None:
                agent = _create_agent(client, tools, checkpointer=checkpointer)
            else:
                agent = _create_react_agent(client, tools, checkpointer=checkpointer)
            from datetime import datetime, UTC
            config = {
                "configurable": {"thread_id": thread_id},
                "metadata": {"created_at": datetime.now(UTC).isoformat()},
            }
            if _trace_enabled():
                _trace_log("langgraph_request", {
                    "model": getattr(client, "model", ""),
                    "base_url": getattr(client, "base_url", ""),
                    "messages": _serialize_messages([HumanMessage(content=prompt)]),
                    "thread_id": thread_id,
                })
            if _debug_payload_enabled():
                payload = {
                    "model": getattr(client, "model", ""),
                    "base_url": getattr(client, "base_url", ""),
                    "messages": _serialize_messages([HumanMessage(content=prompt)]),
                    "tools": _tool_debug_summary(tools, include_schema=True),
                    "thread_id": thread_id,
                }
                _debug_log(payload)
            result = agent.invoke(
                {"messages": [HumanMessage(content=prompt)]},
                config=config,
            )
            if _trace_enabled():
                _trace_log("langgraph_response", {
                    "messages": _serialize_messages(result.get("messages", [])),
                })
            messages = result.get("messages", [])
            if _debug_enabled():
                print("[AGENT_CLI_DEBUG] langgraph_messages")
                print(json.dumps(_serialize_messages(messages), indent=2))
            if fallback_parser:
                tail = messages[-1] if messages else None
                if tail and isinstance(tail, BaseMessage):
                    parsed = _extract_tool_calls_from_text(tail.content or "")
                    if parsed:
                        if _debug_enabled():
                            print(f"[AGENT_CLI_DEBUG] parsed_tool_calls: {parsed}")
                        for call in parsed:
                            tool_name = call.get("name") or "tool"
                            try:
                                tool_fn = next(t for t in tools if t.name == tool_name)
                                result_payload = tool_fn.invoke(call.get("args") or {})
                            except StopIteration:
                                result_payload = {"success": False, "error": f"Unknown tool: {tool_name}"}
                            except Exception as exc:
                                result_payload = {"success": False, "error": str(exc)}
                            messages.append(ToolMessage(content=str(result_payload), tool_call_id=tool_name))
                        followup = _run_tool_fallback(
                            client,
                            tools,
                            messages,
                            max_iters=max(1, args.max_iters - 1),
                            fallback_parser=fallback_parser,
                            invoke_timeout=args.invoke_timeout,
                            invoke_retries=args.invoke_retries,
                            retry_backoff=defaults["retry_backoff"],
                            original_prompt=prompt,
                        )
                        print(followup)
                        return 0
            final = messages[-1].content if messages else ""
            print(final)
            return 0

    try:
        response = _run_loop(
            client, tools, prompt,
            max_iters=args.max_iters,
            fallback_parser=fallback_parser,
            invoke_timeout=args.invoke_timeout,
            invoke_retries=args.invoke_retries,
            retry_backoff=defaults["retry_backoff"],
        )
    except Exception as exc:
        if (
            ResponseError is not None
            and isinstance(exc, ResponseError)
            and "does not support tools" in str(exc)
        ):
            if _debug_enabled():
                print("[AGENT_CLI_DEBUG] tools unsupported; using textual fallback")
            fallback_llm = _build_client(
                model,
                base_url,
                defaults["ssl_verify"],
                defaults["temperature"],
                defaults["seed"],
                http_timeout,
            )
            fallback_response = _run_text_fallback(
                fallback_llm,
                tools,
                prompt,
                max_iters=args.max_iters,
            )
            print(fallback_response)
            return 0
        raise
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
