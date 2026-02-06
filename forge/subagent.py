#!/usr/bin/env python3
"""
Forge Subagent - Wrapper for Claude Code delegation.

Allows Claude Code to delegate tasks to Forge (local Ollama agent).
Useful for:
- Offloading simple coding tasks
- Testing against multiple models
- Running tasks that need local file access
- Self-improving tool development

Usage:
    from forge.subagent import delegate, ForgeSubagent

    # One-shot delegation
    result = delegate("Create a hello.html with CSS animation")

    # With session persistence
    forge = ForgeSubagent(workspace="myproject", model="qwen3-vl:8b")
    result1 = forge.run("Create hello.html")
    result2 = forge.run("Add a button to hello.html")  # Remembers context
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Add parent to path for imports
FORGE_DIR = Path(__file__).parent
sys.path.insert(0, str(FORGE_DIR.parent))


class ForgeSubagent:
    """Subagent wrapper for Forge with session persistence."""

    def __init__(
        self,
        workspace: str = "poc",
        model: str = "gemma3:4b",
        ollama_url: str = "http://localhost:11435",
        max_iters: int = 6,
        timeout: int = 120,
    ):
        """Initialize Forge subagent.

        Args:
            workspace: Workspace name or path
            model: Ollama model to use
            ollama_url: Ollama API URL
            max_iters: Max agent iterations per request
            timeout: Timeout per LLM call
        """
        self.workspace = workspace
        self.model = model
        self.ollama_url = ollama_url
        self.max_iters = max_iters
        self.timeout = timeout
        self._session = None

    def _ensure_session(self):
        """Lazy-load session to avoid import issues."""
        if self._session is None:
            from forge.agent.session import Session
            self._session = Session(model=self.model, max_history=10)
        return self._session

    def run(self, prompt: str, with_context: bool = True) -> dict:
        """Run a task through Forge.

        Args:
        prompt: The task to run
            with_context: If True, use conversation history

        Returns:
            dict with keys:
                - success: bool
                - result: str (agent response)
                - stats: dict (token usage, etc)
                - error: str (if failed)
        """
        try:
            if with_context:
                from forge.agent.runner import run_with_session
                session = self._ensure_session()
                session.add_user_message(prompt)

                result = run_with_session(
                    session=session,
                    prompt=prompt,
                    workspace=self.workspace,
                    ollama_url=self.ollama_url,
                    max_iters=self.max_iters,
                    timeout=self.timeout,
                )

                session.add_assistant_message(result)

                return {
                    "success": True,
                    "result": result,
                    "stats": {
                        "turn": session.stats.turn_count,
                        "tokens": session.stats.total_tokens,
                        "max_context": session.stats.max_context,
                        "context_pct": session.stats.context_pct,
                    },
                }
            else:
                from forge.agent.runner import run_once

                result = run_once(
                    prompt=prompt,
                    workspace=self.workspace,
                    model=self.model,
                    ollama_url=self.ollama_url,
                    max_iters=self.max_iters,
                    timeout=self.timeout,
                )

                return {
                    "success": True,
                    "result": result,
                    "stats": {"turn": 1},
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": "",
            }

    def reset(self) -> None:
        """Reset conversation history."""
        if self._session:
            self._session.reset()

    def get_history(self, last_n: int = 5) -> str:
        """Get recent conversation history."""
        if self._session:
            return self._session.get_history_summary(last_n=last_n)
        return ""

    def add_tool(self, name: str, code: str) -> dict:
        """Add a custom tool to Forge.

        This allows Forge to extend its own capabilities.

        Args:
            name: Tool name
            code: Python code defining the tool function

        Returns:
            Success/error dict
        """
        from forge.tools.registry import get_registry

        registry = get_registry(self.workspace)
        return registry.save_tool(name, code)


def delegate(
    prompt: str,
    workspace: str = "poc",
    model: str = "gemma3:4b",
    ollama_url: str = "http://localhost:11435",
    timeout: int = 120,
) -> str:
    """One-shot delegation to Forge.

    Convenience function for simple delegation without session.

    Args:
        prompt: Task to run
        workspace: Workspace name or path
        model: Ollama model
        ollama_url: Ollama API URL
        timeout: Timeout in seconds

    Returns:
        Agent response string
    """
    from forge.agent.runner import run_once

    return run_once(
        prompt=prompt,
        workspace=workspace,
        model=model,
        ollama_url=ollama_url,
        timeout=timeout,
    )


def delegate_cli(prompt: str, workspace: str = "poc", model: str = "gemma3:4b") -> str:
    """Delegate via CLI subprocess (isolation).

    Runs forge in a separate process for full isolation.
    Slower but safer for untrusted operations.

    Args:
        prompt: Task to run
        workspace: Workspace name
        model: Model to use

    Returns:
        CLI output
    """
    forge_path = FORGE_DIR / "cli.py"

    result = subprocess.run(
        [
            sys.executable,
            str(forge_path),
            "--prompt", prompt,
            "--workspace", workspace,
            "--model", model,
        ],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minute max
    )

    if result.returncode != 0:
        return f"Error: {result.stderr}"

    return result.stdout


# For testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Forge Subagent Test")
    parser.add_argument("prompt", help="Prompt to run")
    parser.add_argument("-w", "--workspace", default="poc")
    parser.add_argument("-m", "--model", default="gemma3:4b")
    args = parser.parse_args()

    result = delegate(args.prompt, workspace=args.workspace, model=args.model)
    print(result)
