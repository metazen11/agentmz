#!/usr/bin/env python3
"""
Minimal LangChain CLI runner for Ollama.

Defaults come from .env. Example:
  python scripts/agent_cli.py --prompt "List files in /workspaces/poc"
"""
import argparse
import json
import os
import re
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

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


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _debug_enabled() -> bool:
    return os.environ.get("AGENT_CLI_DEBUG", "").lower() in {"1", "true", "yes"} or \
        os.environ.get("LC_DEBUG", "").lower() in {"1", "true", "yes"}


def _debug_payload_enabled() -> bool:
    return os.environ.get("AGENT_CLI_DEBUG_PAYLOAD", "").lower() in {"1", "true", "yes"}


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
            if name:
                calls.append({"name": name, "args": args})
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("name"):
                    calls.append({"name": item.get("name"), "args": item.get("arguments") or item.get("args") or {}})
    return calls


def _resolve_defaults(env: dict) -> dict:
    def _truthy(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _bool_with_default(value: str | None, default: bool) -> bool:
        if value is None or value == "":
            return default
        return _truthy(value)

    def _int_or(value: str | None, fallback: int) -> int:
        if value is None or value == "":
            return fallback
        try:
            return int(value)
        except ValueError:
            return fallback

    model = env.get("AGENT_CLI_MODEL") or env.get("AGENT_MODEL") or "qwen3:0.6b"
    base_url = (
        env.get("AGENT_CLI_OLLAMA_BASE")
        or env.get("OLLAMA_API_BASE_LOCAL")
        or env.get("OLLAMA_API_BASE")
        or "http://localhost:11434"
    )
    workspace = env.get("AGENT_CLI_WORKSPACE") or env.get("DEFAULT_WORKSPACE") or "poc"
    project_name = env.get("AGENT_CLI_PROJECT_NAME", "")
    use_langgraph = _truthy(env.get("AGENT_CLI_USE_LANGGRAPH"))
    max_iters = _int_or(env.get("AGENT_CLI_MAX_ITERS"), 6)
    ssl_verify = _bool_with_default(env.get("AGENT_CLI_SSL_VERIFY"), True)
    tool_choice = env.get("AGENT_CLI_TOOL_CHOICE", "").strip() or "auto"
    return {
        "model": model,
        "base_url": base_url,
        "workspace": workspace,
        "project_name": project_name,
        "use_langgraph": use_langgraph,
        "max_iters": max_iters,
        "ssl_verify": ssl_verify,
        "tool_choice": tool_choice,
    }


def _build_client(model: str, base_url: str, ssl_verify: bool):
    if ChatOllama is None:
        raise RuntimeError(
            "langchain-ollama is required. Install with: pip install langchain-ollama"
        )
    client_kwargs = {"verify": ssl_verify}
    return ChatOllama(
        model=model,
        base_url=base_url,
        client_kwargs=client_kwargs,
        sync_client_kwargs=client_kwargs,
        async_client_kwargs=client_kwargs,
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
    ]


def _run_tool_fallback(llm, tools, messages: list[BaseMessage], max_iters: int, fallback_parser: bool) -> str:
    debug = _debug_enabled()
    debug_payload = _debug_payload_enabled()
    tool_map = {t.name: t for t in tools}

    for _ in range(max_iters):
        if debug_payload:
            payload = {
                "model": getattr(llm, "model", ""),
                "base_url": getattr(llm, "base_url", ""),
                "messages": _serialize_messages(messages),
                "tools": _tool_debug_summary(tools, include_schema=True),
            }
            _debug_log(payload)
        response = llm.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None) or []
        if debug and tool_calls:
            print(f"[LC] tool_calls: {tool_calls}")
        if not tool_calls and fallback_parser:
            parsed = _extract_tool_calls_from_text(response.content or "")
            if parsed:
                tool_calls = parsed
                if debug:
                    print(f"[AGENT_CLI_DEBUG] parsed_tool_calls: {tool_calls}")
        if not tool_calls:
            if debug:
                print("[AGENT_CLI_DEBUG] final_response")
                print(response.content or "")
            return response.content or ""

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
            messages.append(ToolMessage(content=str(result), tool_call_id=name or "tool"))
    return "Max iterations reached without final response."


def _run_loop(llm, tools, prompt: str, max_iters: int = 6, fallback_parser: bool = False) -> str:
    debug = _debug_enabled()
    messages = [
        SystemMessage(content=(
            "You MUST use tools for all filesystem operations. "
            "Use list_files, list_tree, or glob to discover files. "
            "Use read_file to inspect contents. "
            "Use write_file to create new files. "
            "Use apply_patch to edit existing files. "
            "Use mkdir, move_file, copy_file, delete_file, stat_path for filesystem changes. "
            "Use run_command only for simple shell commands. "
            "When generating HTML, output valid HTML5 with proper tags and structure."
        )),
        HumanMessage(content=prompt),
    ]
    if debug:
        print("[AGENT_CLI_DEBUG] starting_tool_loop")
    return _run_tool_fallback(llm, tools, messages, max_iters=max_iters, fallback_parser=fallback_parser)


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
    parser.add_argument("--prompt", required=True, help="Prompt to send to the model")
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
    args = parser.parse_args()

    model = args.model
    base_url = args.ollama.rstrip("/")
    prompt = args.prompt

    try:
        client = _build_client(model, base_url, defaults["ssl_verify"])
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
                        )
                        print(followup)
                        return 0
            final = messages[-1].content if messages else ""
            print(final)
            return 0

    response = _run_loop(client, tools, prompt, max_iters=args.max_iters, fallback_parser=fallback_parser)
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
