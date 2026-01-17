#!/usr/bin/env python3
"""
Coding Agent API - exposes aider + tools (grep, glob, bash) as HTTP API.
Uses Python stdlib only (no Flask needed).

Endpoints:
  GET  /health              - Health check
  POST /api/agent/run       - Run full agent loop to complete a task (main entry point)
  POST /api/context         - Get project context for a workspace (NEW)
  POST /api/aider/execute   - Run aider for single code edit
  POST /api/grep            - Search file contents
  POST /api/glob            - Find files by pattern
  POST /api/bash            - Run shell commands
  POST /api/read            - Read file contents

Context Sources (aggregated by ProjectContext):
  - Database: Project/Task records from PostgreSQL
  - Files: project.md (project-level), task.md (task-specific)
  - Discovery: Auto-detected from codebase (languages, frameworks, etc.)

Environment Variables:
  OLLAMA_API_BASE   - Ollama URL (default: http://localhost:11434)
  AIDER_MODEL       - Model for aider edits (default: ollama_chat/qwen3:4b)
  AGENT_MODEL       - Model for orchestration (default: qwen2.5-coder:3b)
  MAX_ITERATIONS    - Max agent loop iterations (default: 20)
  WORKSPACES_DIR    - Base path for workspaces
"""

import fnmatch
import glob as glob_module
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def load_env_file(env_path: str = None):
    """Load environment variables from .env file."""
    if env_path is None:
        # Look for .env in parent directory (v2/.env) or current directory
        script_dir = Path(__file__).parent
        env_path = script_dir.parent / ".env"
        if not env_path.exists():
            env_path = Path.cwd() / ".env"

    if isinstance(env_path, str):
        env_path = Path(env_path)

    if env_path.exists():
        print(f"[CONFIG] Loading {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Don't override existing env vars
                    if key not in os.environ:
                        os.environ[key] = value


# Load .env file before reading config
load_env_file()


class Config:
    """Runtime configuration that can be updated."""

    def __init__(self):
        self.reload()

    def reload(self):
        """Reload config from environment variables."""
        self.ollama_api_base = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
        self.aider_model = os.environ.get("AIDER_MODEL", "ollama_chat/qwen2.5-coder:3b")
        self.agent_model = os.environ.get("AGENT_MODEL", "qwen2.5-coder:3b")
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "20"))
        self.default_workspace = os.environ.get("DEFAULT_WORKSPACE", "poc")
        self.git_user_name = os.environ.get("GIT_USER_NAME", "Aider Agent")
        self.git_user_email = os.environ.get("GIT_USER_EMAIL", "aider@local")

        # Workspaces directory
        workspaces_env = os.environ.get("WORKSPACES_DIR", "")
        if workspaces_env and os.path.isabs(workspaces_env):
            self.workspaces_dir = workspaces_env
        elif os.path.isdir("/v2/workspaces"):
            self.workspaces_dir = "/v2/workspaces"
        elif os.path.isdir("/workspaces"):
            self.workspaces_dir = "/workspaces"
        else:
            self.workspaces_dir = str(Path(__file__).parent.parent / "workspaces")

        # Current active workspace (can be changed at runtime)
        self.current_workspace = self.default_workspace

    def to_dict(self):
        """Return config as dictionary."""
        return {
            "ollama_api_base": self.ollama_api_base,
            "aider_model": self.aider_model,
            "agent_model": self.agent_model,
            "max_iterations": self.max_iterations,
            "default_workspace": self.default_workspace,
            "current_workspace": self.current_workspace,
            "workspaces_dir": self.workspaces_dir,
        }

    def list_workspaces(self):
        """List available workspaces."""
        if not os.path.isdir(self.workspaces_dir):
            return []
        return [
            d for d in os.listdir(self.workspaces_dir)
            if os.path.isdir(os.path.join(self.workspaces_dir, d))
            and not d.startswith(".")
        ]

    def set_workspace(self, workspace: str) -> bool:
        """Set the current workspace. Returns True if valid."""
        # Handle [%root%] variable
        if workspace.startswith("[%root%]"):
            resolved = self.resolve_workspace_path(workspace)
            if os.path.isdir(resolved):
                self.current_workspace = workspace
                return True
            return False
        workspace_path = os.path.join(self.workspaces_dir, workspace)
        if os.path.isdir(workspace_path):
            self.current_workspace = workspace
            return True
        return False

    def resolve_workspace_path(self, workspace: str) -> str:
        """Resolve workspace to absolute path, supporting [%root%] variable.

        Args:
            workspace: Workspace identifier, can be:
                - "[%root%]" -> resolves to PROJECT_ROOT
                - "[%root%]/subdir" -> resolves to PROJECT_ROOT/subdir
                - Absolute path -> used directly
                - Workspace name -> joined with workspaces_dir

        Returns:
            Absolute path to the workspace directory
        """
        # Handle [%root%] variable for self-editing
        if workspace.startswith("[%root%]"):
            # Get PROJECT_ROOT from env, fallback to parent of scripts dir
            root = os.environ.get("PROJECT_ROOT", str(Path(__file__).parent.parent))
            return workspace.replace("[%root%]", root)

        # Handle absolute paths
        if os.path.isabs(workspace):
            return workspace

        # Default: join with workspaces_dir
        return os.path.join(self.workspaces_dir, workspace)


# Global config instance
config = Config()

# Tool definitions for LLM
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a pattern in files. Use this to find code, functions, classes, or any text in the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Subdirectory to search in (default: .)"},
                    "glob": {"type": "string", "description": "File pattern filter like *.py"},
                    "case_insensitive": {"type": "boolean", "description": "Ignore case"},
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a pattern. Use this to discover files in the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern like **/*.py or src/*.js"},
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read contents of a file. Use this to examine code before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "offset": {"type": "integer", "description": "Start line (1-indexed)"},
                    "limit": {"type": "integer", "description": "Max lines to read"},
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command. Use for running tests, checking versions, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (max 300)"},
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create a NEW file that doesn't exist yet. Only use for brand new files. For modifying existing files, use 'edit' instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to workspace"},
                    "content": {"type": "string", "description": "The complete content to write to the file"},
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Modify existing code files using AI-powered diff editing. PREFERRED for all changes to existing files. First read the file, then describe what changes to make.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Description of code changes to make"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "Files to edit"},
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that the task is complete. Call this when finished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["PASS", "FAIL"], "description": "PASS if successful, FAIL if could not complete"},
                    "summary": {"type": "string", "description": "Brief summary of what was done or why it failed"},
                },
                "required": ["status", "summary"]
            }
        }
    }
]


class AiderAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected mid-response; nothing more to do.
            return

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        if self.path == "/health":
            self._send_json({
                "status": "ok",
                "aider_model": config.aider_model,
                "agent_model": config.agent_model,
                "max_iterations": config.max_iterations,
                "ollama_url": config.ollama_api_base,
                "current_workspace": config.current_workspace,
            })
        elif self.path == "/api/models":
            self._send_json(self._list_ollama_models())
        elif self.path == "/api/model/status":
            # Return current model config and loaded model
            loaded_model = self._get_loaded_ollama_model()
            self._send_json({
                "success": True,
                "agent_model": config.agent_model,
                "aider_model": config.aider_model,
                "loaded_model": loaded_model or "none",
                "ollama_api_base": config.ollama_api_base,
            })
        elif self.path == "/api/config":
            self._send_json({
                "success": True,
                "config": config.to_dict(),
                "workspaces": config.list_workspaces(),
            })
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        try:
            if self.path == "/api/aider/execute":
                workspace = data.get("workspace") or config.current_workspace
                prompt = data.get("prompt", "")
                files = data.get("files", [])

                if not prompt:
                    self._send_json({"error": "prompt required"}, 400)
                    return

                timeout = data.get("timeout")
                result = self._run_aider(workspace, prompt, files, timeout)
                self._send_json(result)

            elif self.path == "/api/grep":
                result = self._run_grep(data)
                self._send_json(result)

            elif self.path == "/api/glob":
                result = self._run_glob(data)
                self._send_json(result)

            elif self.path == "/api/bash":
                result = self._run_bash(data)
                self._send_json(result)

            elif self.path == "/api/write":
                result = self._run_write(data)
                self._send_json(result)

            elif self.path == "/api/read":
                result = self._run_read(data)
                self._send_json(result)

            elif self.path == "/api/agent/run":
                result = self._run_agent(data)
                self._send_json(result)

            elif self.path == "/api/config":
                # Update config
                updates = {}
                if "workspace" in data:
                    if config.set_workspace(data["workspace"]):
                        updates["current_workspace"] = config.current_workspace
                    else:
                        self._send_json(
                            {"success": False, "error": f"Workspace not found: {data['workspace']}"},
                            400,
                        )
                        return
                if "agent_model" in data:
                    config.agent_model = data["agent_model"]
                    updates["agent_model"] = config.agent_model
                if "aider_model" in data:
                    config.aider_model = data["aider_model"]
                    updates["aider_model"] = config.aider_model
                if "max_iterations" in data:
                    config.max_iterations = int(data["max_iterations"])
                    updates["max_iterations"] = config.max_iterations

                if updates:
                    updates["success"] = True
                    self._send_json(updates)
                else:
                    self._send_json({"success": True, "config": config.to_dict()})
            elif self.path == "/api/model/switch":
                model = data.get("model")
                timeout = data.get("timeout", 30)
                if not model or not isinstance(model, str):
                    self._send_json({"success": False, "error": "model required"}, 400)
                    return
                try:
                    timeout_seconds = int(timeout)
                except (TypeError, ValueError):
                    timeout_seconds = 30
                timeout_seconds = max(5, min(timeout_seconds, 120))

                previous_agent_model = config.agent_model
                previous_aider_model = config.aider_model

                # Update config to new model
                config.agent_model = model
                config.aider_model = f"ollama_chat/{model}" if not model.startswith("ollama") else model

                print(f"[MODEL] Switching from {previous_agent_model} to {model}")
                print(f"[MODEL] Agent model: {config.agent_model}")
                print(f"[MODEL] Aider model: {config.aider_model}")

                warm_result = self._warm_ollama_model(config.agent_model, timeout_seconds)
                if not warm_result["success"]:
                    print(f"[MODEL] Switch failed: {warm_result.get('error')}")
                    config.agent_model = previous_agent_model
                    config.aider_model = previous_aider_model
                    self._send_json(warm_result, 500)
                    return

                loaded_model = warm_result.get("loaded_model", config.agent_model)
                print(f"[MODEL] Switch successful - loaded: {loaded_model}")

                self._send_json({
                    "success": True,
                    "agent_model": config.agent_model,
                    "aider_model": config.aider_model,
                    "loaded_model": loaded_model,
                    "previous_model": previous_agent_model,
                })

            elif self.path == "/api/context":
                # Get project context for a workspace
                result = self._get_context(data)
                self._send_json(result)

            else:
                self._send_json({"error": "Not found"}, 404)

        except Exception as e:
            try:
                self._send_json({"error": str(e)}, 500)
            except (BrokenPipeError, ConnectionResetError):
                return

    def _list_ollama_models(self) -> dict:
        """Return models available in Ollama."""
        import urllib.request
        import urllib.error

        url = f"{config.ollama_api_base}/api/tags"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [
                m.get("name") for m in payload.get("models", [])
                if isinstance(m, dict) and m.get("name")
            ]
            models.sort()
            return {"success": True, "models": models}
        except urllib.error.HTTPError as exc:
            return {"success": False, "error": f"Ollama HTTP {exc.code}", "models": []}
        except Exception as exc:
            return {"success": False, "error": f"Ollama error: {exc}", "models": []}

    def _run_aider(self, workspace: str, prompt: str, files: list, timeout=None) -> dict:
        """Run aider with the given prompt in the workspace."""
        print(f"[AIDER] Running with model: {config.aider_model}")

        workspace_path = config.resolve_workspace_path(workspace)

        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        # Initialize git if needed
        git_dir = os.path.join(workspace_path, ".git")
        if not os.path.isdir(git_dir):
            subprocess.run(["git", "init"], cwd=workspace_path, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", config.git_user_email],
                cwd=workspace_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", config.git_user_name],
                cwd=workspace_path,
                capture_output=True,
            )
            # Initial commit so aider has something to work with
            subprocess.run(["git", "add", "-A"], cwd=workspace_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace_path, capture_output=True)

        # If no files specified, auto-detect common code files
        if not files:
            for f in os.listdir(workspace_path):
                if f.endswith(('.py', '.js', '.html', '.css', '.json', '.md', '.txt', '.yaml', '.yml')):
                    if not f.startswith('.'):
                        files.append(f)

        # Build aider command
        cmd = [
            "aider",
            "--model", config.aider_model,
            "--no-auto-commits",
            "--yes",  # Auto-confirm
            "--message", prompt,
        ]

        # Add specific files if provided
        for f in files:
            cmd.append(f)

        env = os.environ.copy()
        env["OLLAMA_API_BASE"] = config.ollama_api_base

        try:
            try:
                timeout_seconds = int(timeout) if timeout is not None else 900
            except (TypeError, ValueError):
                timeout_seconds = 900
            timeout_seconds = max(10, min(timeout_seconds, 900))

            result = subprocess.run(
                cmd,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "workspace": workspace,
                "model": config.aider_model
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Aider timed out after {timeout_seconds} seconds"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _warm_ollama_model(self, model: str, timeout_seconds: int) -> dict:
        """Warm Ollama model so the switch is ready before accepting prompts."""
        import urllib.request
        import urllib.error

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{config.ollama_api_base}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("message"):
                # Verify model is actually loaded via /api/ps
                loaded_model = self._get_loaded_ollama_model()
                if loaded_model and loaded_model != model:
                    print(f"[MODEL] Warning: Expected {model} but {loaded_model} is loaded")
                return {"success": True, "loaded_model": loaded_model or model}
            return {"success": False, "error": "Ollama warmup failed - no response message"}
        except urllib.error.HTTPError as exc:
            return {"success": False, "error": f"Ollama HTTP {exc.code}"}
        except Exception as exc:
            return {"success": False, "error": f"Ollama warmup error: {exc}"}

    def _get_loaded_ollama_model(self) -> str:
        """Check which model is currently loaded in Ollama via /api/ps."""
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(f"{config.ollama_api_base}/api/ps")
            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            models = result.get("models", [])
            if models:
                return models[0].get("name", "")
            return ""
        except Exception:
            return ""

    def _run_grep(self, data: dict) -> dict:
        """Search file contents using grep/ripgrep.

        Args:
            pattern: regex pattern to search for (required)
            workspace: workspace name (default: "poc")
            path: subdirectory to search in (optional)
            glob: file pattern filter like "*.py" (optional)
            case_insensitive: ignore case (default: False)
            context: lines of context around matches (default: 0)
        """
        pattern = data.get("pattern")
        workspace = data.get("workspace") or config.current_workspace
        path = data.get("path", ".")
        file_glob = data.get("glob", "")
        case_insensitive = data.get("case_insensitive", False)
        context = data.get("context", 0)

        if not pattern:
            return {"success": False, "error": "pattern required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        search_path = os.path.join(workspace_path, path)
        if not os.path.exists(search_path):
            return {"success": False, "error": f"Path not found: {path}"}

        # Prefer ripgrep if available, fall back to grep
        try:
            subprocess.run(["rg", "--version"], capture_output=True, check=True)
            use_rg = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            use_rg = False

        if use_rg:
            cmd = ["rg", "--json", pattern]
            if case_insensitive:
                cmd.append("-i")
            if context > 0:
                cmd.extend(["-C", str(context)])
            if file_glob:
                cmd.extend(["-g", file_glob])
            cmd.append(search_path)
        else:
            cmd = ["grep", "-rn", pattern]
            if case_insensitive:
                cmd.append("-i")
            if context > 0:
                cmd.extend(["-C", str(context)])
            if file_glob:
                cmd.extend(["--include", file_glob])
            cmd.append(search_path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            matches = []
            if use_rg:
                # Parse ripgrep JSON output
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "match":
                            match_data = entry.get("data", {})
                            matches.append({
                                "file": match_data.get("path", {}).get("text", ""),
                                "line": match_data.get("line_number"),
                                "text": match_data.get("lines", {}).get("text", "").strip()
                            })
                    except json.JSONDecodeError:
                        continue
            else:
                # Parse grep output
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        matches.append({
                            "file": parts[0],
                            "line": int(parts[1]) if parts[1].isdigit() else None,
                            "text": parts[2].strip()
                        })

            return {
                "success": True,
                "matches": matches,
                "count": len(matches),
                "tool": "ripgrep" if use_rg else "grep"
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Search timed out after 30 seconds"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_glob(self, data: dict) -> dict:
        """Find files matching a glob pattern.

        Args:
            pattern: glob pattern like "**/*.py" (required)
            workspace: workspace name (default: "poc")
        """
        pattern = data.get("pattern")
        workspace = data.get("workspace") or config.current_workspace

        if not pattern:
            return {"success": False, "error": "pattern required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        full_pattern = os.path.join(workspace_path, pattern)

        try:
            matches = glob_module.glob(full_pattern, recursive=True)
            # Return paths relative to workspace
            relative_matches = [
                os.path.relpath(m, workspace_path) for m in matches
            ]
            # Sort and limit results
            relative_matches.sort()

            return {
                "success": True,
                "files": relative_matches[:500],  # Limit to 500 files
                "count": len(relative_matches),
                "truncated": len(relative_matches) > 500
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_bash(self, data: dict) -> dict:
        """Run a shell command in the workspace.

        Args:
            command: shell command to run (required)
            workspace: workspace name (default: "poc")
            timeout: timeout in seconds (default: 30, max: 300)
        """
        command = data.get("command")
        workspace = data.get("workspace") or config.current_workspace
        timeout = min(data.get("timeout", 30), 300)  # Max 5 minutes

        if not command:
            return {"success": False, "error": "command required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        # Basic safety: block obviously dangerous commands
        dangerous = ["rm -rf /", "dd if=", "mkfs", ":(){", "fork bomb"]
        cmd_lower = command.lower()
        for d in dangerous:
            if d in cmd_lower:
                return {"success": False, "error": f"Command blocked for safety: {d}"}

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:50000],  # Limit output size
                "stderr": result.stderr[:10000] if result.returncode != 0 else None,
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout} seconds"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_write(self, data: dict) -> dict:
        """Write content to a file.

        Args:
            path: file path relative to workspace (required)
            content: content to write (required)
            workspace: workspace name (default: "poc")
        """
        path = data.get("path")
        content = data.get("content")
        workspace = data.get("workspace") or config.current_workspace

        if not path:
            return {"success": False, "error": "path required"}
        if content is None:
            return {"success": False, "error": "content required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        file_path = os.path.join(workspace_path, path)

        # Security: ensure file is within workspace (or project root for [%root%])
        real_workspace = os.path.realpath(workspace_path)
        # For new files, check parent dir
        parent_dir = os.path.dirname(file_path) or workspace_path
        real_parent = os.path.realpath(parent_dir)
        if not real_parent.startswith(real_workspace):
            return {"success": False, "error": "Access denied: path outside workspace"}

        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(file_path) or workspace_path, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "path": path,
                "bytes_written": len(content.encode("utf-8")),
                "workspace": workspace
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_read(self, data: dict) -> dict:
        """Read file contents.

        Args:
            path: file path relative to workspace (required)
            workspace: workspace name (default: "poc")
            offset: line number to start from (optional, 1-indexed)
            limit: max lines to read (optional, default: all)
        """
        path = data.get("path")
        workspace = data.get("workspace") or config.current_workspace
        offset = data.get("offset", 1)
        limit = data.get("limit")

        if not path:
            return {"success": False, "error": "path required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        file_path = os.path.join(workspace_path, path)

        # Security: ensure file is within workspace (or project root for [%root%])
        real_workspace = os.path.realpath(workspace_path)
        real_file = os.path.realpath(file_path)
        if not real_file.startswith(real_workspace):
            return {"success": False, "error": "Access denied: path outside workspace"}

        if not os.path.isfile(file_path):
            return {"success": False, "error": f"File not found: {path}"}

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Apply offset (1-indexed)
            start_idx = max(0, offset - 1)
            lines = lines[start_idx:]

            # Apply limit
            if limit:
                lines = lines[:limit]

            content = "".join(lines)

            # Limit content size
            if len(content) > 100000:
                content = content[:100000]
                truncated = True
            else:
                truncated = False

            return {
                "success": True,
                "content": content,
                "lines": len(lines),
                "total_lines": total_lines,
                "truncated": truncated
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_context(self, data: dict) -> dict:
        """Get project context for a workspace.

        Args:
            workspace: Workspace name (optional, uses current if not provided)
            project_id: Optional project ID for database context
            task_id: Optional task ID for current task context

        Returns:
            Project context as dictionary
        """
        workspace = data.get("workspace") or config.current_workspace
        project_id = data.get("project_id")
        task_id = data.get("task_id")

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        try:
            from project_context import ProjectContext

            ctx = ProjectContext(workspace_path=workspace_path)
            ctx.load_all(project_id=project_id, task_id=task_id)

            return {
                "success": True,
                "workspace": workspace,
                "context": ctx.to_dict(),
            }
        except ImportError:
            return {"success": False, "error": "ProjectContext module not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_system_prompt(self, workspace: str, workspace_path: str,
                               project_id: int = None, task_id: int = None) -> str:
        """Build system prompt using ProjectContext.

        Uses the ProjectContext class to aggregate context from:
        - Database (Project/Task records)
        - Explicit files (project.md, task.md)
        - Auto-discovery (ProjectDiscovery)
        - Workspace file listing (always included)

        Args:
            workspace: Workspace name
            workspace_path: Absolute path to workspace
            project_id: Optional project ID for database context
            task_id: Optional task ID for current task context

        Returns:
            Complete system prompt string
        """
        # Get workspace file listing for context
        file_listing = self._get_workspace_files(workspace_path)

        try:
            from project_context import ProjectContext

            ctx = ProjectContext(workspace_path=workspace_path)
            ctx.load_all(project_id=project_id, task_id=task_id)
            base_prompt = ctx.build_system_prompt()
            # Append file listing to provide workspace context
            return base_prompt + "\n\n" + file_listing

        except ImportError:
            print("[AGENT] Warning: project_context.py not available, using minimal prompt")
            return self._minimal_system_prompt() + "\n\n" + file_listing

        except Exception as e:
            print(f"[AGENT] Warning: Context build failed: {e}, using minimal prompt")
            return self._minimal_system_prompt() + "\n\n" + file_listing

    def _minimal_system_prompt(self) -> str:
        """Fallback minimal system prompt if ProjectContext fails."""
        return """You are a coding agent. You have access to tools to explore and modify code.

Available tools:
- grep: Search for patterns in files
- glob: Find files by pattern
- read: Read file contents
- bash: Run shell commands
- write: Create NEW files only (files that don't exist yet)
- edit: Modify EXISTING files using AI diff editing (PREFERRED for changes)
- done: Signal task completion

TOOL SELECTION (IMPORTANT):
- For EXISTING files: Always use 'edit' - it preserves unchanged code
- For NEW files: Use 'write' to create them
- Before editing: Always 'read' the file first to understand its structure

Workflow:
1. First, explore the workspace to understand the codebase (use glob, read)
2. Search for relevant code (use grep)
3. Make necessary changes (use edit for existing files, write for new files)
4. Verify changes work (use bash to run tests)
5. Call done(status="PASS", summary="...") when complete

For simple tasks (create a file, write content), just do it directly.
For complex tasks (modify existing code, find bugs), explore first to understand the codebase."""

    def _get_workspace_files(self, workspace_path: str, max_depth: int = 2) -> str:
        """Get a formatted list of files in the workspace for agent context.

        Args:
            workspace_path: Absolute path to the workspace directory
            max_depth: Maximum directory depth to traverse (default: 2)

        Returns:
            Formatted string listing workspace files
        """
        lines = ["## Workspace Files\n"]

        # Directories to skip
        skip_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv',
                     'env', '.env', 'dist', 'build', '.pytest_cache', '.mypy_cache'}

        for root, dirs, files in os.walk(workspace_path):
            # Skip hidden and common non-essential dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')
                       and d not in skip_dirs]

            depth = root.replace(workspace_path, '').count(os.sep)
            if depth >= max_depth:
                dirs.clear()  # Don't go deeper
                continue

            indent = '  ' * depth
            rel_path = os.path.relpath(root, workspace_path)

            if rel_path != '.':
                lines.append(f"{indent}{os.path.basename(root)}/")

            # Sort files and limit per directory (include dotfiles, devs need to see config)
            sorted_files = sorted(files)
            for file in sorted_files[:20]:  # Limit files per dir
                lines.append(f"{indent}  {file}")

            # Stop if we've accumulated too many lines
            if len(lines) >= 100:
                lines.append("  ... (truncated)")
                break

        return '\n'.join(lines[:100])  # Cap total lines

    def _clean_summary(self, summary: str) -> str:
        """Clean up agent summary for successful completions.

        Removes misleading prefixes that small models sometimes add
        after recovering from errors.

        Args:
            summary: Raw summary string from the agent

        Returns:
            Cleaned summary string
        """
        if not summary:
            return summary

        # Patterns that shouldn't prefix a successful response
        error_prefixes = [
            "Error:",
            "Error -",
            "ERROR:",
            "Failed:",
            "Failure:",
        ]

        cleaned = summary.strip()
        for prefix in error_prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        return cleaned

    def _run_agent(self, data: dict) -> dict:
        """Run the full agent loop to complete a task.

        Args:
            task: Description of what to accomplish (required)
            workspace: workspace name (default: "poc")
            max_iterations: Override default max iterations (optional)
            project_id: Project ID for fetching task history (optional)
            task_id: Current task ID for context (optional)
        """
        import urllib.request
        import urllib.error

        task = data.get("task")
        workspace = data.get("workspace") or config.current_workspace
        max_iter = min(data.get("max_iterations", config.max_iterations), 50)
        project_id = data.get("project_id")
        task_id = data.get("task_id")

        if not task:
            return {"success": False, "error": "task required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        # Build system prompt with full project context (DB + files + discovery)
        system_prompt = self._build_system_prompt(
            workspace=workspace,
            workspace_path=workspace_path,
            project_id=project_id,
            task_id=task_id
        )

        # Build initial message
        user_message = f"""Task: {task}

Workspace: {workspace}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Agent loop
        iteration = 0
        all_tool_calls = []
        result = {"success": False, "status": "INCOMPLETE", "summary": "Agent did not complete", "iterations": 0}

        while iteration < max_iter:
            iteration += 1
            print(f"[AGENT] Iteration {iteration}/{max_iter}")

            # Call Ollama
            try:
                ollama_response = self._call_ollama(messages)
            except Exception as e:
                result["error"] = f"Ollama error: {str(e)}"
                break

            if not ollama_response:
                result["error"] = "No response from Ollama"
                break

            response_message = ollama_response.get("message", {})
            content = response_message.get("content", "")
            tool_calls = response_message.get("tool_calls", [])

            if content:
                print(f"[AGENT] Response: {content[:200]}...")

            # Handle tool calls in content (some models return JSON instead of tool_calls)
            if not tool_calls and content:
                tool_calls = self._parse_tool_calls_from_content(content)

            if not tool_calls:
                # No tools called, check if done
                if "done" in content.lower() and ("pass" in content.lower() or "complete" in content.lower()):
                    result = {"success": True, "status": "PASS", "summary": self._clean_summary(content), "iterations": iteration}
                else:
                    # Agent stopped without calling done
                    result["summary"] = content or "Agent stopped without completing"
                break

            # Execute tool calls
            tool_results = []
            for tool_call in tool_calls:
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                tool_args = func.get("arguments", {})

                # Parse arguments if they're a string
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                print(f"[AGENT] Tool: {tool_name}({json.dumps(tool_args)[:100]})")

                # Execute the tool
                tool_output = self._execute_agent_tool(tool_name, tool_args, workspace)

                all_tool_calls.append({
                    "iteration": iteration,
                    "tool": tool_name,
                    "args": tool_args,
                    "output": tool_output[:1000] if isinstance(tool_output, str) else str(tool_output)[:1000],
                })

                # Check for done signal
                if tool_name == "done":
                    status = tool_args.get("status", "PASS")
                    summary = tool_args.get("summary", "Task completed")
                    # Clean up summary for successful completions
                    if status == "PASS":
                        summary = self._clean_summary(summary)
                    result = {
                        "success": status == "PASS",
                        "status": status,
                        "summary": summary,
                        "iterations": iteration,
                        "tool_calls": all_tool_calls,
                    }
                    return result

                tool_results.append({
                    "role": "tool",
                    "content": json.dumps(tool_output) if isinstance(tool_output, dict) else str(tool_output),
                })

            # Add to message history
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })
            for tr in tool_results:
                messages.append(tr)

        # Max iterations reached
        result["iterations"] = iteration
        result["tool_calls"] = all_tool_calls
        if iteration >= max_iter:
            result["error"] = f"Max iterations ({max_iter}) reached"

        return result

    def _call_ollama(self, messages: list) -> dict:
        """Call Ollama API with messages and tools."""
        import urllib.request
        import urllib.error

        print(f"[AGENT] Calling Ollama with model: {config.agent_model}")

        payload = {
            "model": config.agent_model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
        }

        req = urllib.request.Request(
            f"{config.ollama_api_base}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                # Log which model actually responded
                if result.get("model"):
                    print(f"[AGENT] Response from model: {result.get('model')}")
                return result
        except urllib.error.URLError as e:
            print(f"[AGENT] Ollama error: {e}")
            return None
        except Exception as e:
            print(f"[AGENT] Error: {e}")
            return None

    def _parse_tool_calls_from_content(self, content: str) -> list:
        """Parse tool calls from content when model returns JSON instead of tool_calls."""
        import re
        tool_calls = []
        content = content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            content = "\n".join(lines).strip()

        def extract_tool_call(data: dict) -> dict:
            """Extract tool name and args from various formats models might return."""
            # Standard format: {"name": "tool", "arguments": {...}}
            if "name" in data:
                return {
                    "function": {
                        "name": data.get("name"),
                        "arguments": data.get("arguments", data.get("parameters", {})),
                    }
                }
            # Simple format: {"type": "tool", ...args}
            if "type" in data and isinstance(data.get("type"), str):
                args = {k: v for k, v in data.items() if k not in {"type", "name"}}
                return {
                    "function": {
                        "name": data.get("type"),
                        "arguments": args,
                    }
                }
            # Alternative format: {"function": "tool", "arguments": {...}}
            if "function" in data and isinstance(data.get("function"), str):
                return {
                    "function": {
                        "name": data.get("function"),
                        "arguments": data.get("arguments", data.get("parameters", {})),
                    }
                }
            # Nested format: {"function": {"name": "tool", "arguments": {...}}}
            if "function" in data and isinstance(data.get("function"), dict):
                func = data.get("function", {})
                return {
                    "function": {
                        "name": func.get("name"),
                        "arguments": func.get("arguments", {}),
                    }
                }
            return None

        # Try to parse as JSON object
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                tc = extract_tool_call(data)
                if tc:
                    tool_calls.append(tc)
                    return tool_calls
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        tc = extract_tool_call(item)
                        if tc:
                            tool_calls.append(tc)
                return tool_calls
        except json.JSONDecodeError:
            pass

        # Try to parse <tools>...</tools> blocks
        tools_blocks = re.findall(r"<tools>(.*?)</tools>", content, re.DOTALL)
        for block in tools_blocks:
            block = block.strip()
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                tc = extract_tool_call(data)
                if tc:
                    tool_calls.append(tc)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        tc = extract_tool_call(item)
                        if tc:
                            tool_calls.append(tc)
        if tool_calls:
            return tool_calls

        # Try to find JSON objects in content
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

    def _execute_agent_tool(self, tool_name: str, args: dict, workspace: str) -> dict:
        """Execute a tool and return the result."""
        args["workspace"] = workspace

        if tool_name == "grep":
            return self._run_grep(args)
        elif tool_name == "glob":
            return self._run_glob(args)
        elif tool_name == "read":
            return self._run_read(args)
        elif tool_name == "bash":
            return self._run_bash(args)
        elif tool_name == "write":
            return self._run_write(args)
        elif tool_name == "edit":
            # Use aider for edits
            prompt = args.get("prompt", "")
            files = args.get("files", [])
            return self._run_aider(workspace, prompt, files)
        elif tool_name == "done":
            # Done is handled in the main loop
            return {"status": args.get("status", "PASS"), "summary": args.get("summary", "")}
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    def log_message(self, format, *args):
        print(f"[AIDER-API] {args[0]}")


def main():
    port = int(os.environ.get("PORT", 8001))
    server = HTTPServer(("0.0.0.0", port), AiderAPIHandler)
    print(f"[AIDER-API] Starting on port {port}")
    print(f"[AIDER-API] Aider Model: {config.aider_model}")
    print(f"[AIDER-API] Agent Model: {config.agent_model}")
    print(f"[AIDER-API] Ollama: {config.ollama_api_base}")
    print(f"[AIDER-API] Workspaces: {config.workspaces_dir}")
    print(f"[AIDER-API] Default Workspace: {config.current_workspace}")
    server.serve_forever()


if __name__ == "__main__":
    main()
