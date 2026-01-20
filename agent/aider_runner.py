"""Agent runner using Aider API for code editing.

Uses the containerized Aider API which connects to Ollama.
Model can be switched via AIDER_MODEL environment variable.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

# Configuration
AIDER_API_URL = os.getenv("AIDER_API_URL", "http://localhost:8001")
WORKSPACES_DIR = Path(__file__).parent.parent / "workspaces"


def run_agent(
    workspace_name: str,
    task_title: str,
    task_description: str,
    task_id: int,
    node_name: str = "dev",
    files: list = None,
) -> dict:
    """Run the Aider agent to complete a task.

    Args:
        workspace_name: Name of workspace folder under v2/workspaces/
        task_title: Title of the task
        task_description: Description of what to do
        task_id: Database ID of the task
        node_name: Current pipeline node (pm, dev, qa, security, documentation)
        files: Optional list of files to edit

    Returns:
        dict with status (PASS/FAIL), summary, and output
    """
    workspace_path = WORKSPACES_DIR / workspace_name
    pipeline_dir = workspace_path / ".pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    # Build prompt based on node
    node_context = {
        "pm": "You are a project planner. Clarify scope, break down work, and outline risks.",
        "dev": "You are a developer. Implement the requested feature or fix.",
        "qa": "You are a QA engineer. Test the implementation and verify it works.",
        "security": "You are a security reviewer. Identify risks and verify protections.",
        "documentation": "You are a technical writer. Document changes and how to validate them.",
    }

    prompt = f"""{node_context.get(node_name, node_context['dev'])}

Task: {task_title}

{task_description}

Please complete this task. Create or modify files as needed."""

    # Call Aider API
    try:
        response = call_aider(workspace_name, prompt, files or [])

        if response.get("success"):
            result = {
                "status": "PASS",
                "summary": f"Completed: {task_title}",
                "output": response.get("output", ""),
                "model": response.get("model", "unknown"),
            }
        else:
            result = {
                "status": "FAIL",
                "summary": response.get("error", "Aider failed"),
                "output": response.get("output", ""),
                "model": response.get("model", "unknown"),
            }

    except Exception as e:
        result = {
            "status": "FAIL",
            "summary": f"Error: {str(e)}",
            "output": "",
        }

    # Write result.json
    write_result(pipeline_dir, result, task_id)
    return result


def call_aider(workspace: str, prompt: str, files: list) -> dict:
    """Call the Aider API.

    When running in Docker (root compose), v2 workspaces are at /workspaces/v2/.
    When running locally (v2 scripts/aider_api.py), workspaces are directly accessible.
    """
    try:
        # Check if we're calling Docker-mounted Aider or local Aider
        # Local v2 aider_api.py serves workspaces directly (no v2/ prefix needed)
        # Root Docker aider-api mounts v2/workspaces at /workspaces/v2/
        in_docker = os.path.isdir("/workspaces")
        container_workspace = f"v2/{workspace}" if in_docker else workspace

        response = httpx.post(
            f"{AIDER_API_URL}/api/aider/execute",
            json={
                "workspace": container_workspace,
                "prompt": prompt,
                "files": files,
            },
            timeout=900,  # 15 minute timeout for slow local LLMs
        )
        response.raise_for_status()
        return response.json()

    except httpx.TimeoutException:
        return {"success": False, "error": "Aider API timeout (>15 minutes)"}
    except httpx.ConnectError:
        return {"success": False, "error": f"Cannot connect to Aider API at {AIDER_API_URL}"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_result(pipeline_dir: Path, result: dict, task_id: int):
    """Write result.json to the pipeline directory."""
    result_data = {
        "task_id": task_id,
        "status": result["status"],
        "summary": result["summary"],
        "output": result.get("output", ""),
        "model": result.get("model", ""),
        "timestamp": datetime.now().isoformat(),
    }
    result_path = pipeline_dir / "result.json"
    result_path.write_text(json.dumps(result_data, indent=2))
    print(f"Wrote result to {result_path}")


def check_aider_health() -> dict:
    """Check if Aider API is healthy and get current model."""
    try:
        response = httpx.get(f"{AIDER_API_URL}/health", timeout=5)
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) < 2:
        # Check health
        print("Aider API Health:", check_aider_health())
    else:
        workspace = sys.argv[1]
        result = run_agent(
            workspace_name=workspace,
            task_title="Create hello.txt",
            task_description="Create a file called hello.txt with 'Hello from Aider!'",
            task_id=0,
            node_name="dev",
        )
        print(f"\nResult: {json.dumps(result, indent=2)}")
