#!/usr/bin/env python3
"""
Run agent_cli across models to create index_{model}.html files.

Usage:
  python tests/run_model_create_html.py --models qwen3:1.7b,deepseek-r1:7b
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


DEFAULT_MODELS = [
    "deepseek-r1:7b",
    "qwen3:1.7b",
    "qwen2.5-coder:3b",
    "gemma3:4b",
    "qwen3:0.6b",
]

DEFAULT_PROMPT = (
    "Create index.html in the workspace with valid HTML5. "
    "Include an H1 element with class animated and text Hello World, "
    "plus CSS keyframes applied to .animated. No external scripts. "
    "Use write_file."
)


def _parse_models(value: str) -> list[str]:
    if not value:
        return DEFAULT_MODELS
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_name(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def _run_agent(workspace: Path, model: str, prompt: str, env: dict) -> int:
    from scripts import agent_cli

    argv = [
        "agent_cli.py",
        "--prompt",
        prompt,
        "--model",
        model,
        "--project-name",
        f"model-{_safe_name(model)}",
        "--max-iters",
        "4",
    ]
    old_argv = sys.argv[:]
    old_env = os.environ.copy()
    old_cwd = os.getcwd()
    try:
        os.environ.update(env)
        os.chdir(workspace)
        sys.argv = argv
        return agent_cli.main()
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create model-specific HTML outputs.")
    parser.add_argument("--models", default="", help="Comma-separated model list")
    parser.add_argument("--workspace", default="workspaces/poc")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    if not workspace.exists():
        print(f"Workspace not found: {workspace}")
        return 1

    env = os.environ.copy()
    env.setdefault("AGENT_CLI_DEBUG", "1")
    env.setdefault("AGENT_CLI_DEBUG_PAYLOAD", "1")
    env.setdefault("AGENT_CLI_SSL_VERIFY", "0")
    env.setdefault("AGENT_CLI_TOOL_CHOICE", "any")
    env.setdefault("AGENT_CLI_TOOL_FALLBACK", "1")

    models = _parse_models(args.models)
    index_path = workspace / "index.html"
    for model in models:
        if index_path.exists():
            index_path.unlink()
        print(f"\n=== Running model: {model} ===")
        code = _run_agent(workspace, model, args.prompt, env)
        if code != 0:
            print(f"Model run failed: {model} (exit {code})")
            continue
        if not index_path.exists():
            print(f"index.html not created for model: {model}")
            continue
        target = workspace / f"index_{_safe_name(model)}.html"
        shutil.copyfile(index_path, target)
        print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
