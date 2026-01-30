#!/usr/bin/env python3
"""
Forge Runner - Thin wrapper around agent_cli for model-agnostic testing.

Forge is the agent name; implementation stays system-agnostic.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _trace_enabled() -> bool:
    return os.environ.get("FORGE_TRACE", "").lower() in {"1", "true", "yes"}


def _trace_log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[FORGE_TRACE {timestamp}] {message}")


def _resolve_defaults(env: dict) -> dict:
    def _truthy(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "on"}

    model = env.get("FORGE_MODEL") or env.get("AGENT_CLI_MODEL") or env.get("AGENT_MODEL") or "qwen3:0.6b"
    base_url = (
        env.get("FORGE_OLLAMA_BASE")
        or env.get("AGENT_CLI_OLLAMA_BASE")
        or env.get("OLLAMA_API_BASE_LOCAL")
        or env.get("OLLAMA_API_BASE")
        or "http://localhost:11434"
    )
    workspace = env.get("FORGE_WORKSPACE") or env.get("AGENT_CLI_WORKSPACE") or env.get("DEFAULT_WORKSPACE") or "poc"
    project_name = env.get("FORGE_PROJECT_NAME") or env.get("AGENT_CLI_PROJECT_NAME") or workspace
    use_langgraph = _truthy(env.get("FORGE_USE_LANGGRAPH") or env.get("AGENT_CLI_USE_LANGGRAPH"))
    max_iters = env.get("FORGE_MAX_ITERS") or env.get("AGENT_CLI_MAX_ITERS") or "6"
    invoke_timeout = env.get("FORGE_INVOKE_TIMEOUT") or env.get("AGENT_CLI_INVOKE_TIMEOUT") or "120"
    invoke_retries = env.get("FORGE_INVOKE_RETRIES") or env.get("AGENT_CLI_INVOKE_RETRIES") or "2"
    return {
        "model": model,
        "base_url": base_url,
        "workspace": workspace,
        "project_name": project_name,
        "use_langgraph": use_langgraph,
        "max_iters": max_iters,
        "invoke_timeout": invoke_timeout,
        "invoke_retries": invoke_retries,
    }


def main() -> int:
    _load_env()
    defaults = _resolve_defaults(os.environ)
    parser = argparse.ArgumentParser(description="Run Forge (wrapper around agent_cli)")
    parser.add_argument("--prompt", help="Prompt to send to Forge")
    parser.add_argument("--prompt-file", help="Path to a file containing the prompt")
    parser.add_argument("--model", default=defaults["model"])
    parser.add_argument("--ollama", default=defaults["base_url"])
    parser.add_argument("--workspace", default=defaults["workspace"])
    parser.add_argument("--project-name", default=defaults["project_name"])
    parser.add_argument("--max-iters", default=defaults["max_iters"])
    parser.add_argument("--invoke-timeout", default=defaults["invoke_timeout"],
                        help="Timeout in seconds for each LLM invoke (default: 120)")
    parser.add_argument("--invoke-retries", default=defaults["invoke_retries"],
                        help="Number of retries on timeout (default: 2)")
    parser.add_argument("--use-langgraph", action="store_true", default=defaults["use_langgraph"])
    args = parser.parse_args()

    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "agent_cli.py"),
    ]
    if args.prompt_file:
        cmd.extend(["--prompt-file", args.prompt_file])
    else:
        if not args.prompt:
            print("Prompt is required (use --prompt or --prompt-file)")
            return 1
        cmd.extend(["--prompt", args.prompt])
    cmd += [
        "--model",
        args.model,
        "--ollama",
        args.ollama,
        "--workspace",
        args.workspace,
        "--project-name",
        args.project_name,
        "--max-iters",
        str(args.max_iters),
        "--invoke-timeout",
        str(args.invoke_timeout),
        "--invoke-retries",
        str(args.invoke_retries),
    ]
    if args.use_langgraph:
        cmd.append("--use-langgraph")

    if _trace_enabled():
        _trace_log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if _trace_enabled():
        _trace_log(f"Exit code: {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
