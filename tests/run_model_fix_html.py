#!/usr/bin/env python3
"""
Run agent_cli across models to fix HTML output to be HTML5 compliant.

Usage:
  python tests/run_model_fix_html.py --models qwen3:1.7b,deepseek-r1:7b
"""
from __future__ import annotations

import argparse
import os
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
    "First call read_file on index.html, then apply_patch to make it valid HTML5. "
    "Ensure a <h1 class=\"animated\">Hello World</h1> exists in <body>. "
    "Do not use write_file or delete_file. Use apply_patch."
)


def _parse_models(value: str) -> list[str]:
    if not value:
        return DEFAULT_MODELS
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_name(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def _is_html5_valid(content: str) -> bool:
    lowered = content.lower()
    if "<!doctype html" not in lowered:
        return False
    if "<html" not in lowered or "</html>" not in lowered:
        return False
    if "<head" not in lowered or "</head>" not in lowered:
        return False
    if "<body" not in lowered or "</body>" not in lowered:
        return False
    if "<class" in lowered:
        return False
    return True


def _run_agent(workspace: Path, model: str, prompt: str, env: dict) -> int:
    from scripts import agent_cli

    argv = [
        "agent_cli.py",
        "--prompt",
        prompt,
        "--model",
        model,
        "--project-name",
        f"model-fix-{_safe_name(model)}",
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
    parser = argparse.ArgumentParser(description="Fix model HTML outputs to be HTML5 compliant.")
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
    for model in models:
        source = workspace / f"index_{_safe_name(model)}.html"
        if not source.exists():
            print(f"Missing source for model: {model}")
            continue
        print(f"\n=== Fixing model: {model} ===")
        working = workspace / "index.html"
        working.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        code = _run_agent(workspace, model, args.prompt, env)
        if code != 0:
            print(f"Fix run failed: {model} (exit {code})")
            continue
        fixed_content = working.read_text(encoding="utf-8")
        target = workspace / f"index_{_safe_name(model)}_fixed.html"
        target.write_text(fixed_content, encoding="utf-8")
        ok = _is_html5_valid(fixed_content)
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
