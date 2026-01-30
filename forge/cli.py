#!/usr/bin/env python3
"""Forge CLI - Launch TUI or run single prompt."""
import os
import sys
from typing import Optional

import typer

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = typer.Typer(
    name="forge",
    help="Forge TUI - Local-first agentic coding environment",
    add_completion=False,
)


@app.command()
def main(
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt", "-p",
        help="Prompt to run (enables yolo mode)",
    ),
    prompt_file: Optional[str] = typer.Option(
        None,
        "--file", "-f",
        help="Read prompt from file (enables yolo mode)",
    ),
    workspace: str = typer.Option(
        "poc",
        "--workspace", "-w",
        help="Workspace name or path",
        envvar="FORGE_WORKSPACE",
    ),
    model: str = typer.Option(
        "gemma3:4b",
        "--model", "-m",
        help="Ollama model to use",
        envvar="FORGE_MODEL",
    ),
    ollama_url: str = typer.Option(
        "http://localhost:11435",
        "--ollama",
        help="Ollama API base URL",
        envvar="FORGE_OLLAMA_BASE",
    ),
    max_iters: int = typer.Option(
        6,
        "--max-iters",
        help="Maximum agent iterations",
        envvar="FORGE_MAX_ITERS",
    ),
    timeout: int = typer.Option(
        120,
        "--timeout",
        help="Timeout per LLM call (seconds)",
        envvar="FORGE_INVOKE_TIMEOUT",
    ),
):
    """
    Forge - Local-first agentic coding environment.

    Run with no args for interactive TUI, or use -p/-f for single prompts.

    Examples:

        forge                           # Interactive TUI
        forge -p "Create hello.html"    # Single prompt
        forge -f task.txt -w myproject  # Prompt from file
    """
    # Determine prompt source
    actual_prompt = None
    if prompt_file:
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                actual_prompt = f.read().strip()
        except FileNotFoundError:
            typer.echo(f"Error: File not found: {prompt_file}", err=True)
            raise typer.Exit(1)
    elif prompt:
        actual_prompt = prompt

    # If prompt provided, run yolo mode
    if actual_prompt:
        from forge.agent.runner import run_once

        result = run_once(
            prompt=actual_prompt,
            workspace=workspace,
            model=model,
            ollama_url=ollama_url,
            max_iters=max_iters,
            timeout=timeout,
        )
        typer.echo(result)
    else:
        # Interactive TUI mode
        from forge.app import ForgeApp

        forge_app = ForgeApp(
            workspace=workspace,
            model=model,
            ollama_url=ollama_url,
            max_iters=max_iters,
            timeout=timeout,
        )
        forge_app.run()


if __name__ == "__main__":
    app()
