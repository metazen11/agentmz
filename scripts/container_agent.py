#!/usr/bin/env python3
"""
Container Agent - Uses Ollama native tool calling.

The LLM directly calls tools - no text parsing.
Reads context.json for task info, writes result.json on completion.
"""

import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

# Configuration
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL = os.environ.get("MODEL", "qwen3:4b")  # Good balance of quality and speed
WORKSPACE = Path("/workspace")
PIPELINE_DIR = WORKSPACE / ".pipeline"

# Track files changed during execution
files_changed = []

# Define tools the LLM can call
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the workspace directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Subdirectory path (default: current directory)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of file to read"
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates or overwrites)",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the workspace",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    }
]


def log(msg):
    """Log with timestamp."""
    print(f"[AGENT] {msg}", flush=True)


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return result."""
    log(f"TOOL CALL: {name}({json.dumps(args)})")

    try:
        if name == "list_files":
            path = WORKSPACE / args.get("path", ".")
            files = list(path.iterdir())
            result = "\n".join(f.name for f in files)
            log(f"RESULT: {result}")
            return result or "(empty directory)"

        elif name == "read_file":
            filepath = WORKSPACE / args["filename"]
            content = filepath.read_text()
            log(f"RESULT: Read {len(content)} bytes from {args['filename']}")
            return content

        elif name == "write_file":
            filepath = WORKSPACE / args["filename"]
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(args["content"])
            # Track file change for result.json
            files_changed.append(args["filename"])
            log(f"RESULT: Wrote {len(args['content'])} bytes to {args['filename']}")
            return f"Successfully wrote {args['filename']}"

        elif name == "run_command":
            import subprocess
            result = subprocess.run(
                args["command"],
                shell=True,
                cwd=WORKSPACE,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout + result.stderr
            log(f"RESULT: {output[:200]}")
            return output or "(no output)"

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        log(f"ERROR: {e}")
        return f"Error: {e}"


def chat_with_tools(prompt: str, max_iterations: int = 10):
    """Chat with LLM using tool calling."""

    messages = [
        {"role": "user", "content": prompt}
    ]

    for i in range(max_iterations):
        log(f"--- Iteration {i+1} ---")

        # Call Ollama chat API with tools
        response = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": MODEL,
                "messages": messages,
                "tools": TOOLS,
                "stream": False
            },
            timeout=300
        )
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        log(f"LLM response: {content[:200] if content else '(no text)'}")
        log(f"Tool calls (native): {len(tool_calls)}")

        # Parse tool calls from content if not in tool_calls field
        if not tool_calls and content:
            import re
            # Look for JSON in content (with or without markdown)
            json_match = re.search(r'\{[^{}]*"name"[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    if "name" in parsed:
                        tool_calls = [{"function": parsed}]
                        log(f"Tool calls (parsed from content): {len(tool_calls)}")
                except json.JSONDecodeError:
                    pass

        # If no tool calls, we're done
        if not tool_calls:
            log("No more tool calls - done")
            return content

        # Add assistant message to history
        messages.append(message)

        # Execute each tool call
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})

            # Handle args as string or dict
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except:
                    args = {}

            # Execute and get result
            result = execute_tool(name, args)

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "content": result
            })

    log("Max iterations reached")
    return "Max iterations reached"


def read_context():
    """Read context.json if it exists (written by Director)."""
    context_path = PIPELINE_DIR / "context.json"
    if context_path.exists():
        try:
            return json.loads(context_path.read_text())
        except Exception as e:
            log(f"Warning: Failed to read context.json: {e}")
    return None


def write_result(status: str, summary: str, details: str = "", task_id: str = None, task_db_id: int = None):
    """Write result.json for Director to read.

    Args:
        status: "PASS" or "FAIL"
        summary: Brief summary of what was done
        details: Detailed output or error message
        task_id: Task ID string (e.g. "T001") for routing verification
        task_db_id: Task database ID for routing verification
    """
    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "status": status,
        "summary": summary,
        "details": details,
        "files_changed": list(set(files_changed)),  # Dedupe
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
    }
    # Include task identifiers for Director routing verification
    if task_id:
        result["task_id"] = task_id
    if task_db_id:
        result["task_db_id"] = task_db_id
    result_path = PIPELINE_DIR / "result.json"
    result_path.write_text(json.dumps(result, indent=2))
    log(f"Result written to {result_path}")


def main():
    prompt = os.environ.get("PROMPT", "")
    task_id = None
    task_db_id = None

    # Try to read context from Director
    context = read_context()
    if context:
        task_id = context.get('task_id')
        task_db_id = context.get('task_db_id')
        log(f"Context loaded: task={task_id}, node={context.get('node')}")
        # Use prompt from context if available
        if context.get('prompt_override'):
            prompt = context['prompt_override']
        elif not prompt:
            # Build prompt from task info
            prompt = f"Task: {context.get('title', 'Unknown')}\n\nDescription: {context.get('description', 'No description')}"
            if context.get('acceptance_criteria'):
                prompt += "\n\nAcceptance Criteria:\n"
                for i, ac in enumerate(context['acceptance_criteria'], 1):
                    prompt += f"  {i}. {ac}\n"

    if not prompt:
        log("ERROR: No PROMPT set and no context.json found")
        write_result("FAIL", "No prompt provided", "Agent requires PROMPT env var or .pipeline/context.json",
                    task_id=task_id, task_db_id=task_db_id)
        sys.exit(1)

    log(f"Task: {prompt[:200]}...")
    log(f"Workspace: {WORKSPACE}")
    log(f"Model: {MODEL}")
    log("=" * 50)

    try:
        result = chat_with_tools(prompt)
        log("=" * 50)
        log(f"Final response: {result[:500] if result else '(empty)'}")

        # Determine success (simple heuristic)
        status = "PASS"
        if "error" in result.lower() or "failed" in result.lower() or "cannot" in result.lower():
            status = "FAIL"

        write_result(status, result[:500] if result else "Task completed", result,
                    task_id=task_id, task_db_id=task_db_id)

    except Exception as e:
        log(f"FATAL ERROR: {e}")
        write_result("FAIL", f"Agent error: {str(e)}", str(e),
                    task_id=task_id, task_db_id=task_db_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
