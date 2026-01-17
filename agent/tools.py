"""Agent tools for file operations and task completion."""
import os
import subprocess
from pathlib import Path
from typing import Optional

# Workspace path will be set when agent starts
WORKSPACE: Optional[Path] = None


def set_workspace(path: str):
    """Set the workspace path for all tools."""
    global WORKSPACE
    WORKSPACE = Path(path)


def list_files(path: str = ".") -> str:
    """List files in a directory."""
    if not WORKSPACE:
        return "Error: Workspace not set"

    target = WORKSPACE / path
    if not target.exists():
        return f"Error: {path} does not exist"
    if not target.is_dir():
        return f"Error: {path} is not a directory"

    try:
        files = []
        for item in sorted(target.iterdir()):
            prefix = "[D]" if item.is_dir() else "[F]"
            files.append(f"{prefix} {item.name}")
        return "\n".join(files) if files else "(empty directory)"
    except Exception as e:
        return f"Error listing files: {e}"


def read_file(path: str) -> str:
    """Read file contents."""
    if not WORKSPACE:
        return "Error: Workspace not set"

    filepath = WORKSPACE / path
    if not filepath.exists():
        return f"Error: {path} not found"
    if not filepath.is_file():
        return f"Error: {path} is not a file"

    try:
        return filepath.read_text()
    except Exception as e:
        return f"Error reading file: {e}"


def edit_file(path: str, search: str, replace: str) -> str:
    """Apply search/replace edit to a file.

    This is the key tool that uses diff-based editing instead of full overwrites.
    The LLM must specify exactly what text to find and what to replace it with.
    """
    if not WORKSPACE:
        return "Error: Workspace not set"

    filepath = WORKSPACE / path

    # Create new file if search is empty
    if not search:
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(replace)
            return f"Created {path}"
        except Exception as e:
            return f"Error creating file: {e}"

    # File must exist for edits
    if not filepath.exists():
        return f"Error: {path} not found. Use empty 'search' to create new file."

    try:
        content = filepath.read_text()
        if search not in content:
            # Provide helpful context about what's in the file
            lines = content.split("\n")[:10]
            preview = "\n".join(lines)
            return f"Error: Search text not found in {path}.\nFirst 10 lines:\n{preview}"

        # Replace first occurrence only (for precise edits)
        new_content = content.replace(search, replace, 1)
        filepath.write_text(new_content)
        return f"Edited {path}: replaced '{search[:50]}...' with '{replace[:50]}...'"
    except Exception as e:
        return f"Error editing file: {e}"


def run_command(command: str) -> str:
    """Execute a shell command in the workspace."""
    if not WORKSPACE:
        return "Error: Workspace not set"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return f"Command failed (exit {result.returncode}):\n{output}"
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds"
    except Exception as e:
        return f"Error running command: {e}"


# Tool definitions for Ollama native tool calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a path. Returns file names prefixed with [F] for files and [D] for directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to workspace (default: '.')",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to workspace",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a file using search and replace. To create a new file, use empty 'search' and put content in 'replace'. For edits, specify exact text to find and replace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to workspace",
                    },
                    "search": {
                        "type": "string",
                        "description": "Exact text to find (empty string to create new file)",
                    },
                    "replace": {
                        "type": "string",
                        "description": "Text to replace with (or full content for new file)",
                    },
                },
                "required": ["path", "search", "replace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command in the workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that the task is complete. Call this when you have finished the work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PASS", "FAIL"],
                        "description": "PASS if task completed successfully, FAIL if unable to complete",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of what was done or why it failed",
                    },
                },
                "required": ["status", "summary"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    if name == "list_files":
        return list_files(arguments.get("path", "."))
    elif name == "read_file":
        return read_file(arguments["path"])
    elif name == "edit_file":
        return edit_file(
            arguments["path"],
            arguments["search"],
            arguments["replace"],
        )
    elif name == "run_command":
        return run_command(arguments["command"])
    elif name == "done":
        # Return special marker for done signal
        return f"__DONE__|{arguments['status']}|{arguments['summary']}"
    else:
        return f"Error: Unknown tool '{name}'"
