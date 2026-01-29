#!/usr/bin/env python3
"""
Minimal LangChain CLI runner for Ollama.

Defaults come from .env. Example:
  python scripts/agent_cli.py --prompt "List files in /workspaces/poc"
"""
import argparse
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent
except Exception:  # pragma: no cover - import guard
    ChatOllama = None
    tool = None
    create_react_agent = None


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _resolve_defaults(env: dict) -> dict:
    def _truthy(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "on"}

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
    return {
        "model": model,
        "base_url": base_url,
        "workspace": workspace,
        "project_name": project_name,
        "use_langgraph": use_langgraph,
        "max_iters": max_iters,
    }


def _build_client(model: str, base_url: str):
    if ChatOllama is None:
        raise RuntimeError(
            "langchain-ollama is required. Install with: pip install langchain-ollama"
        )
    return ChatOllama(model=model, base_url=base_url)


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
        return {"success": True, "files": entries, "count": len(entries)}

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
        return {
            "success": True,
            "path": path,
            "start": start,
            "lines": len(slice_lines),
            "total_lines": len(all_lines),
            "content": "".join(slice_lines),
        }

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
        return {"success": True, "count": len(matches), "matches": matches}

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
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    return [list_files, read_file, grep, run_command]


def _run_loop(llm, tools, prompt: str, max_iters: int = 6) -> str:
    debug = os.environ.get("LC_DEBUG", "").lower() in {"1", "true", "yes"}
    messages = [
        SystemMessage(content=(
            "You can only see files by calling tools. "
            "Use list_files to list directories. "
            "Use read_file for contents. "
            "Use run_command for simple shell commands."
        )),
        HumanMessage(content=prompt),
    ]

    for _ in range(max_iters):
        response = llm.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None) or []
        if debug and tool_calls:
            print(f"[LC] tool_calls: {tool_calls}")
        if not tool_calls:
            return response.content or ""
        tool_map = {t.name: t for t in tools}
        for call in tool_calls:
            name = call.get("name")
            args = call.get("args") or {}
            tool_fn = tool_map.get(name)
            if not tool_fn:
                messages.append(ToolMessage(content=f"Unknown tool: {name}", tool_call_id=call.get("id", name)))
                continue
            try:
                result = tool_fn.invoke(args)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            messages.append(ToolMessage(content=str(result), tool_call_id=call.get("id", name)))
    return "Max iterations reached without final response."


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
        client = _build_client(model, base_url)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    workspace_root = _resolve_workspace(args.workspace)
    tools = _build_tools(workspace_root)
    client = client.bind_tools(tools)

    if args.use_langgraph:
        if create_react_agent is None:
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
            agent = create_react_agent(client, tools, checkpointer=checkpointer)
            from datetime import datetime, UTC
            config = {
                "configurable": {"thread_id": thread_id},
                "metadata": {"created_at": datetime.now(UTC).isoformat()},
            }
            result = agent.invoke(
                {"messages": [HumanMessage(content=prompt)]},
                config=config,
            )
            messages = result.get("messages", [])
            final = messages[-1].content if messages else ""
            print(final)
            return 0

    response = _run_loop(client, tools, prompt, max_iters=args.max_iters)
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
