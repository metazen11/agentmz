#!/usr/bin/env python3
"""
Container Orchestrator - Iterative agent that breaks tasks into atomic steps.

Runs coding tasks in a loop:
1. Plan: Break task into atomic steps
2. Execute: Run each step in container
3. Validate: Check if output works
4. Fix: If broken, send back with error context
5. Repeat until success or max retries

Usage:
    python container_orchestrator.py "Create an Ollama chat UI" /workspaces/poc
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path

# Configuration
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("MODEL", "qwen2.5-coder:3b")
MAX_RETRIES = 3
DOCKER_IMAGE = "agentic-coder:latest"


def call_ollama(prompt: str, system: str = None) -> str:
    """Call Ollama directly for planning (not in container)."""
    import requests

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 1024}
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        print(f"[ORCH] Ollama error: {e}")
        return ""


def plan_atomic_tasks(goal: str) -> list:
    """Break a goal into atomic tasks using LLM."""
    system = """You are a task planner. Break the goal into small, atomic coding tasks.
Each task should create or modify ONE thing.
Output as a JSON array of strings. Example:
["Create index.html with basic structure", "Add dark CSS styles", "Add input form"]
Only output the JSON array, nothing else."""

    response = call_ollama(f"Goal: {goal}", system)

    # Parse JSON from response
    try:
        # Find JSON array in response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            tasks = json.loads(response[start:end])
            return tasks
    except json.JSONDecodeError:
        pass

    # Fallback: single task
    return [goal]


def run_container_task(workspace: str, prompt: str, context_size: int = 4096) -> dict:
    """Run a single task in the container."""
    cmd = [
        "docker", "run", "--rm",
        "-e", f"PROMPT={prompt}",
        "-e", f"OLLAMA_HOST=http://host.docker.internal:11434",
        "-e", f"CONTEXT_SIZE={context_size}",
        "-e", f"MAX_TOKENS=2048",
        "-e", f"MODEL={MODEL}",
        "-v", f"{workspace}:/workspace",
        DOCKER_IMAGE
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}


def validate_html(workspace: str, filename: str) -> dict:
    """Basic validation of HTML file."""
    filepath = Path(workspace) / filename

    if not filepath.exists():
        return {"valid": False, "error": f"File {filename} not found"}

    content = filepath.read_text()
    errors = []

    # Basic checks
    if "<!DOCTYPE html>" not in content and "<html" not in content:
        errors.append("Missing HTML structure")

    if "<script>" in content:
        # Check for common JS issues
        if "fetch(" in content and "await" in content and "async" not in content:
            errors.append("Using await without async function")
        if "stream: true" in content or "stream:true" in content:
            if "reader" not in content.lower():
                errors.append("Streaming enabled but no stream reader")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def fix_task(workspace: str, original_task: str, error_context: str) -> str:
    """Generate a fix prompt based on errors."""
    # Read current files
    workspace_path = Path(workspace)
    files = list(workspace_path.glob("*.html")) + list(workspace_path.glob("*.js"))

    file_contents = ""
    for f in files[:3]:  # Limit to 3 files
        content = f.read_text()[:2000]  # Limit content
        file_contents += f"\n--- {f.name} ---\n{content}\n"

    return f"""Fix the following issue:

ORIGINAL TASK: {original_task}

CURRENT FILES:
{file_contents}

ERRORS FOUND:
{error_context}

Create fixed version of the file(s). Make sure to:
1. Fix all the errors mentioned
2. Keep the existing functionality
3. Use proper async/await for fetch calls
4. Handle Ollama streaming responses correctly (stream: false for simplicity)"""


def run_iterative_task(goal: str, workspace: str, max_retries: int = MAX_RETRIES):
    """Run task with planning, execution, validation, and retry loop."""
    print(f"[ORCH] Goal: {goal}")
    print(f"[ORCH] Workspace: {workspace}")
    print(f"[ORCH] Planning atomic tasks...")

    # Step 1: Plan
    tasks = plan_atomic_tasks(goal)
    print(f"[ORCH] Planned {len(tasks)} atomic tasks:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task}")

    # Step 2: Execute each task
    for i, task in enumerate(tasks, 1):
        print(f"\n[ORCH] === Task {i}/{len(tasks)}: {task[:60]}... ===")

        retries = 0
        current_prompt = task

        while retries < max_retries:
            print(f"[ORCH] Attempt {retries + 1}/{max_retries}")

            # Execute
            result = run_container_task(workspace, current_prompt)

            if not result["success"]:
                print(f"[ORCH] Container failed: {result.get('error', result.get('stderr', 'Unknown'))}")
                retries += 1
                continue

            print(result["stdout"])

            # Validate (for HTML files)
            html_files = list(Path(workspace).glob("*.html"))
            all_valid = True
            error_context = ""

            for html_file in html_files:
                validation = validate_html(workspace, html_file.name)
                if not validation["valid"]:
                    all_valid = False
                    errors = validation.get("errors", [validation.get("error", "Unknown")])
                    error_context += f"{html_file.name}: {', '.join(errors)}\n"
                    print(f"[ORCH] Validation failed for {html_file.name}: {errors}")

            if all_valid:
                print(f"[ORCH] Task {i} completed successfully!")
                break

            # Generate fix prompt
            retries += 1
            if retries < max_retries:
                print(f"[ORCH] Generating fix prompt...")
                current_prompt = fix_task(workspace, task, error_context)

        if retries >= max_retries:
            print(f"[ORCH] Task {i} failed after {max_retries} retries")

    # Summary
    print(f"\n[ORCH] === Complete ===")
    print(f"[ORCH] Files in workspace:")
    for f in Path(workspace).iterdir():
        if not f.name.startswith("."):
            print(f"  - {f.name} ({f.stat().st_size} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Iterative container orchestrator")
    parser.add_argument("goal", help="The task to accomplish")
    parser.add_argument("workspace", help="Path to workspace directory")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES, help="Max retries per task")

    args = parser.parse_args()

    workspace = os.path.abspath(args.workspace)
    if not os.path.isdir(workspace):
        print(f"Error: Workspace {workspace} does not exist")
        sys.exit(1)

    run_iterative_task(args.goal, workspace, args.retries)


if __name__ == "__main__":
    main()
