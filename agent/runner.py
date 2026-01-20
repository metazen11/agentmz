"""Agent runner with Ollama native tool calling."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from .tools import TOOL_DEFINITIONS, execute_tool, set_workspace

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("AGENT_MODEL", "qwen2.5-coder:7b")  # or phi4, llama3.2:3b
MAX_ITERATIONS = 20
TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "120"))


def parse_tool_calls_from_content(content: str) -> list:
    """Parse tool calls from content when model returns JSON instead of tool_calls.

    Some models like qwen return tool calls as JSON in the content field:
    {"name": "list_files", "arguments": {"path": "."}}
    """
    tool_calls = []
    content = content.strip()

    # Try to parse as JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "name" in data:
            # Single tool call
            tool_calls.append({
                "function": {
                    "name": data.get("name"),
                    "arguments": data.get("arguments", {}),
                }
            })
        elif isinstance(data, list):
            # Multiple tool calls
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    tool_calls.append({
                        "function": {
                            "name": item.get("name"),
                            "arguments": item.get("arguments", {}),
                        }
                    })
    except json.JSONDecodeError:
        # Try to find JSON objects in the content
        import re
        json_pattern = r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*[^{}]*\}'
        matches = re.findall(json_pattern, content)
        for match in matches:
            try:
                data = json.loads(match)
                if "name" in data:
                    tool_calls.append({
                        "function": {
                            "name": data.get("name"),
                            "arguments": data.get("arguments", {}),
                        }
                    })
            except json.JSONDecodeError:
                pass

    return tool_calls


def run_agent(
    workspace_path: str,
    task_title: str,
    task_description: str,
    task_id: int,
    node_name: str = "dev",
) -> dict:
    """Run the agent to complete a task.

    Args:
        workspace_path: Path to the workspace directory
        task_title: Title of the task
        task_description: Description of what to do
        task_id: Database ID of the task
        node_name: Current pipeline node (pm, dev, qa, security, documentation)

    Returns:
        dict with status (PASS/FAIL), summary, and details
    """
    set_workspace(workspace_path)
    pipeline_dir = Path(workspace_path) / ".pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    # Build system prompt based on node
    node_prompts = {
        "pm": "You are a project planner. Clarify scope, break down work, and outline risks.",
        "dev": "You are a developer agent. Implement the requested feature or fix the bug. Write clean, working code.",
        "qa": "You are a QA agent. Test the implementation. Run any tests, check for edge cases, verify functionality works.",
        "security": "You are a security reviewer. Identify risks and verify protections.",
        "documentation": "You are a technical writer. Document changes and how to validate them.",
    }
    system_prompt = node_prompts.get(node_name, node_prompts["dev"])

    # Build the initial message
    user_message = f"""Task: {task_title}

Description: {task_description}

Workspace: {workspace_path}

Instructions:
1. First, explore the workspace to understand the codebase
2. Then implement the required changes
3. Use edit_file with search/replace for precise edits (or empty search to create new files)
4. When done, call the 'done' tool with status PASS (success) or FAIL (if you couldn't complete it)

Start by listing the files in the workspace."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Run the agent loop
    iteration = 0
    result = {"status": "FAIL", "summary": "Agent did not complete", "details": ""}
    all_tool_calls = []

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")

        # Call Ollama with tools
        response = call_ollama(messages)

        if not response:
            result["summary"] = "Failed to get response from Ollama"
            break

        # Check for tool calls
        tool_calls = response.get("message", {}).get("tool_calls", [])
        content = response.get("message", {}).get("content", "")

        if content:
            print(f"Agent: {content[:200]}...")

        # Some models (like qwen) return tool calls as JSON in content
        if not tool_calls and content:
            tool_calls = parse_tool_calls_from_content(content)

        if not tool_calls:
            # No tools called, agent is done or stuck
            if "done" in content.lower():
                result["status"] = "PASS"
                result["summary"] = content
            break

        # Process tool calls
        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("function", {}).get("arguments", {})

            print(f"Tool: {tool_name}({json.dumps(tool_args)[:100]})")

            # Execute the tool
            tool_output = execute_tool(tool_name, tool_args)
            all_tool_calls.append({
                "tool": tool_name,
                "args": tool_args,
                "output": tool_output[:500],
            })

            # Check for done signal
            if tool_output.startswith("__DONE__"):
                parts = tool_output.split("|")
                result["status"] = parts[1]
                result["summary"] = parts[2] if len(parts) > 2 else ""
                result["details"] = json.dumps(all_tool_calls, indent=2)

                # Write result.json
                write_result(pipeline_dir, result, task_id)
                return result

            tool_results.append({
                "tool_call_id": tool_call.get("id", ""),
                "role": "tool",
                "content": tool_output,
            })

        # Add assistant message and tool results to history
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })
        for tr in tool_results:
            messages.append(tr)

    # Agent didn't call done() - write failure result
    result["details"] = json.dumps(all_tool_calls, indent=2)
    write_result(pipeline_dir, result, task_id)
    return result


def call_ollama(messages: list) -> Optional[dict]:
    """Call Ollama API with messages and tools."""
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": messages,
                "tools": TOOL_DEFINITIONS,
                "stream": False,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        print(f"Timeout calling Ollama (>{TIMEOUT}s)")
        return None
    except httpx.HTTPStatusError as e:
        print(f"HTTP error from Ollama: {e.response.status_code}")
        return None
    except httpx.ConnectError:
        print(f"Cannot connect to Ollama at {OLLAMA_URL}")
        return None
    except Exception as e:
        print(f"Error calling Ollama: {type(e).__name__}: {e}")
        return None


def write_result(pipeline_dir: Path, result: dict, task_id: int):
    """Write result.json to the pipeline directory."""
    result_data = {
        "task_id": task_id,
        "status": result["status"],
        "summary": result["summary"],
        "details": result.get("details", ""),
        "timestamp": datetime.now().isoformat(),
    }
    result_path = pipeline_dir / "result.json"
    result_path.write_text(json.dumps(result_data, indent=2))
    print(f"Wrote result to {result_path}")


if __name__ == "__main__":
    # Simple test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agent.runner <workspace_path>")
        sys.exit(1)

    workspace = sys.argv[1]
    result = run_agent(
        workspace_path=workspace,
        task_title="Test Task",
        task_description="Create a simple hello.txt file with 'Hello, World!' content",
        task_id=0,
        node_name="dev",
    )
    print(f"\nResult: {result}")
