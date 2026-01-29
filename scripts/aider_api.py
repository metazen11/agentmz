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
  AGENT_MODEL       - Model for orchestration (default: qwen3:1.7b)
  MAX_ITERATIONS    - Max agent loop iterations (default: 20)
  WORKSPACES_DIR    - Base path for workspaces
"""

import fnmatch
import glob as glob_module
import json
import base64
import uuid
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import ssl
import re
import time


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
        self.aider_model = os.environ.get("AIDER_MODEL", "ollama_chat/qwen3:1.7b")
        self.agent_model = os.environ.get("AGENT_MODEL", "qwen3:1.7b")
        self.vision_model = os.environ.get("VISION_MODEL", "")
        self.vision_model_regex = os.environ.get(
            "VISION_MODEL_REGEX",
            r"(^|[\\/:_-])(vl|vision|llava|mllama|moondream|minicpm-v|qwen2\\.5vl|qwen2-vl|qwen-vl|clip)",
        )
        vision_models_raw = os.environ.get("VISION_MODELS", "")
        self.vision_models = [
            model.strip() for model in vision_models_raw.split(",") if model.strip()
        ]
        self.vision_image_max_size = self._parse_int_env("VISION_IMAGE_MAX_SIZE", 640)
        self.vision_max_tokens = self._parse_int_env("VISION_MAX_TOKENS", 120)
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "20"))
        self.default_workspace = os.environ.get("DEFAULT_WORKSPACE", "poc")
        self.git_user_name = os.environ.get("GIT_USER_NAME", "Aider Agent")
        self.git_user_email = os.environ.get("GIT_USER_EMAIL", "aider@local")

        # Workspaces directory
        workspaces_env = os.environ.get("WORKSPACES_DIR", "")
        if workspaces_env and os.path.isabs(workspaces_env):
            self.workspaces_dir = workspaces_env
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
            "vision_model": self.vision_model,
            "vision_models": self.vision_models,
            "vision_model_regex": self.vision_model_regex,
            "vision_image_max_size": self.vision_image_max_size,
            "vision_max_tokens": self.vision_max_tokens,
            "max_iterations": self.max_iterations,
            "default_workspace": self.default_workspace,
            "current_workspace": self.current_workspace,
            "workspaces_dir": self.workspaces_dir,
        }

    def _parse_int_env(self, key: str, default: int) -> int:
        raw = os.environ.get(key)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return value

    def list_workspaces(self):
        """List available workspaces."""
        if not os.path.isdir(self.workspaces_dir):
            return []
        return [
            d for d in os.listdir(self.workspaces_dir)
            if os.path.isdir(os.path.join(self.workspaces_dir, d))
            and not d.startswith(".")
        ]

    def _normalize_workspace_input(self, workspace: str) -> str:
        """Normalize workspace input to a safe relative path under workspaces_dir."""
        if not workspace:
            return ""
        cleaned = str(workspace).replace("\\", "/").strip()
        if cleaned.startswith("[%root%]"):
            return cleaned
        if cleaned.startswith("/workspaces/"):
            cleaned = cleaned[len("/workspaces/"):]
        if cleaned.startswith("workspaces/"):
            cleaned = cleaned[len("workspaces/"):]
        marker = "/workspaces/"
        lowered = cleaned.lower()
        idx = lowered.rfind(marker)
        if idx != -1:
            return cleaned[idx + len(marker):].strip("/")
        if os.path.isabs(cleaned) or re.match(r"^[A-Za-z]:/", cleaned):
            return os.path.basename(cleaned)
        cleaned = re.sub(r"^\.?/?(workspaces/)?", "", cleaned)
        return cleaned.strip("/")

    def set_workspace(self, workspace: str) -> bool:
        """Set the current workspace. Returns True if valid."""
        normalized = self._normalize_workspace_input(workspace)
        if not normalized:
            return False
        # Handle [%root%] variable
        if normalized.startswith("[%root%]"):
            resolved = self.resolve_workspace_path(normalized)
            if os.path.isdir(resolved):
                self.current_workspace = normalized
                return True
            return False
        workspace_path = self.resolve_workspace_path(normalized)
        if os.path.isdir(workspace_path):
            self.current_workspace = normalized
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
        normalized = self._normalize_workspace_input(workspace)

        # Handle [%root%] variable for self-editing
        if normalized.startswith("[%root%]"):
            # Get PROJECT_ROOT from env, fallback to /app or parent of scripts dir
            root = os.environ.get("PROJECT_ROOT")
            if not root:
                root = "/app" if os.path.isdir("/app") else str(Path(__file__).parent.parent)
            return normalized.replace("[%root%]", root)

        if not normalized:
            return self.workspaces_dir

        # Default: join with workspaces_dir
        return os.path.join(self.workspaces_dir, normalized)


# Global config instance
config = Config()


def _ollama_ssl_context():
    verify_ssl = os.environ.get("OLLAMA_VERIFY", "0").lower() in {"1", "true", "yes", "y"}
    if config.ollama_api_base.startswith("https") and not verify_ssl:
        return ssl._create_unverified_context()
    return None

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
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_subtask",
            "description": "Delegate a subtask to another agent. Use when a task is complex and can be broken into independent parts. The subtask runs in the same workspace and returns its result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Brief title for the subtask"},
                    "description": {"type": "string", "description": "Detailed description of what the subtask should accomplish"},
                    "wait": {"type": "boolean", "description": "Whether to wait for subtask completion (default: true)"},
                },
                "required": ["title", "description"]
            }
        }
    }
]


class AiderAPIHandler(BaseHTTPRequestHandler):
    def _log_system_prompt_override(self, prompt: str) -> None:
        if not prompt:
            return
        debug_enabled = os.environ.get("DEBUG", "").strip() == "1"
        logging_level = os.environ.get("LOGGING", "").strip().lower()
        if not (debug_enabled and logging_level == "verbose"):
            return
        raw_max = os.environ.get("SYSTEM_PROMPT_LOG_MAX", "4000")
        try:
            max_len = int(raw_max)
        except ValueError:
            max_len = 4000
        max_len = max(0, max_len)
        truncated = max_len > 0 and len(prompt) > max_len
        preview = prompt if max_len == 0 or not truncated else prompt[:max_len] + "\n...[truncated]"

        print(f"[AGENT] System prompt override length: {len(prompt)}")
        print("[AGENT] System prompt override (begin)")
        print(preview)
        if truncated:
            print("[AGENT] System prompt override (truncated)")
        print("[AGENT] System prompt override (end)")

    def _normalize_path(self, workspace_path: str, path: str) -> str:
        """Normalize tool paths to stay relative to the workspace root."""
        if not path:
            return path
        cleaned = path.lstrip("/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
        if cleaned.startswith("app/") and not os.path.isdir(os.path.join(workspace_path, "app")):
            cleaned = cleaned[len("app/"):]
        return cleaned

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
                workspace_path = config.resolve_workspace_path(workspace)
                files = [
                    self._normalize_path(workspace_path, f) for f in files
                    if isinstance(f, str) and f.strip()
                ]
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

            elif self.path == "/api/vision/describe":
                result = self._describe_image(data)
                self._send_json(result)

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
            context = _ollama_ssl_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
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
            "--auto-commits",
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
            "tools": TOOL_DEFINITIONS,
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
            context = _ollama_ssl_context()
            with urllib.request.urlopen(req, timeout=timeout_seconds, context=context) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("message"):
                # Verify model is actually loaded via /api/ps
                loaded_model = self._get_loaded_ollama_model()
                if loaded_model and loaded_model != model:
                    print(f"[MODEL] Warning: Expected {model} but {loaded_model} is loaded")
                return {"success": True, "loaded_model": loaded_model or model}
            return {"success": False, "error": "Ollama warmup failed - no response message"}
        except urllib.error.HTTPError as exc:
            error_detail = self._extract_ollama_http_error(exc)
            return {
                "success": False,
                "error": error_detail or f"Ollama HTTP {exc.code}",
                "status_code": exc.code,
            }
        except Exception as exc:
            return {"success": False, "error": f"Ollama warmup error: {exc}"}

    def _get_loaded_ollama_model(self) -> str:
        """Check which model is currently loaded in Ollama via /api/ps."""
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(f"{config.ollama_api_base}/api/ps")
            context = _ollama_ssl_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                result = json.loads(response.read().decode("utf-8"))
            models = result.get("models", [])
            if models:
                return models[0].get("name", "")
            return ""
        except Exception:
            return ""

    def _describe_image(self, data: dict) -> dict:
        """Describe an image using the configured vision model."""
        filename = data.get("filename", "image.png")
        b64_data = data.get("data", "")
        context = data.get("context", "")
        compact = bool(data.get("compact", True))
        requested_model = data.get("model")

        if not b64_data or not isinstance(b64_data, str):
            return {"success": False, "error": "image data required"}

        if requested_model is not None and not isinstance(requested_model, str):
            return {"success": False, "error": "vision model must be a string"}

        if requested_model:
            if config.vision_models:
                if requested_model not in config.vision_models:
                    return {"success": False, "error": f"vision model not allowed: {requested_model}"}
            else:
                try:
                    import re
                    if not re.search(config.vision_model_regex, requested_model, re.IGNORECASE):
                        return {"success": False, "error": f"vision model not allowed: {requested_model}"}
                except re.error:
                    return {"success": False, "error": "vision model regex invalid"}

        try:
            raw = base64.b64decode(b64_data)
        except Exception:
            return {"success": False, "error": "invalid base64 data"}

        if len(raw) > 5 * 1024 * 1024:
            return {"success": False, "error": "image too large (max 5MB)"}

        safe_name = os.path.basename(filename) or "image.png"
        tmp_dir = "/tmp/vision_uploads"
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}_{safe_name}")
        try:
            with open(tmp_path, "wb") as f:
                f.write(raw)
            try:
                from mcp_vision_server import analyze_image
            except Exception as exc:
                return {"success": False, "error": f"vision module unavailable: {exc}"}
            selected_model = requested_model or config.vision_model or None
            return analyze_image(tmp_path, context=context, compact=compact, model=selected_model)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

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

        normalized_path = self._normalize_path(workspace_path, path)
        file_path = os.path.join(workspace_path, normalized_path)

        # Security: ensure file is within workspace (or project root for [%root%])
        real_workspace = os.path.realpath(workspace_path)
        real_file = os.path.realpath(file_path)
        if not real_file.startswith(real_workspace):
            return {"success": False, "error": "Access denied: path outside workspace"}

        if not os.path.isfile(file_path):
            return {"success": False, "error": f"File not found: {normalized_path}"}

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
        try:
            from project_context import ProjectContext

            ctx = ProjectContext(workspace_path=workspace_path)
            ctx.load_all(project_id=project_id, task_id=task_id)
            base_prompt = ctx.build_system_prompt()
            file_listing = self._get_workspace_files(workspace_path, key_files=ctx.key_files)
            # Append file listing to provide workspace context
            return base_prompt + ("\n\n" + file_listing if file_listing else "")

        except ImportError:
            print("[AGENT] Warning: project_context.py not available, using minimal prompt")
            file_listing = self._get_workspace_files(workspace_path)
            return self._minimal_system_prompt() + ("\n\n" + file_listing if file_listing else "")

        except Exception as e:
            print(f"[AGENT] Warning: Context build failed: {e}, using minimal prompt")
            file_listing = self._get_workspace_files(workspace_path)
            return self._minimal_system_prompt() + ("\n\n" + file_listing if file_listing else "")

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
- delegate_subtask: Delegate a subtask to another agent (for complex multi-part tasks)
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

Paths:
- All tool paths are relative to the workspace root.
- Do not prefix paths with "app/" unless that directory exists in the workspace.

For simple tasks (create a file, write content), just do it directly.
For complex tasks (modify existing code, find bugs), explore first to understand the codebase."""

    def _minimal_chat_system_prompt(self) -> str:
        """A simple system prompt for direct chat interactions."""
        return """You are a helpful coding assistant. Respond to user questions or commands directly.
Do not output tool calls unless specifically instructed to perform an action (e.g., "grep for X", "read Y").
If you need to perform actions, use the available tools:
- grep: Search for patterns in files
- glob: Find files by pattern
- read: Read file contents
- bash: Run a shell command
- edit: Modify existing code files
- write: Create new files
- delegate_subtask: Delegate a subtask to another agent
"""

    def _get_workspace_files(self, workspace_path: str, key_files: list | None = None) -> str:
        """Return a compact workspace overview for agent context."""
        lines = ["## Workspace Overview"]

        try:
            entries = sorted(os.listdir(workspace_path))
        except OSError:
            return "## Workspace Overview\n(unavailable)"

        # Directories to skip
        skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv",
                     "env", ".env", "dist", "build", ".pytest_cache", ".mypy_cache"}

        dirs = []
        files = []
        for entry in entries:
            full_path = os.path.join(workspace_path, entry)
            if os.path.isdir(full_path):
                if entry.startswith(".") or entry in skip_dirs:
                    continue
                dirs.append(entry)
            elif os.path.isfile(full_path):
                files.append(entry)

        max_items = 12
        if dirs:
            suffix = " ..." if len(dirs) > max_items else ""
            lines.append(f"Top-level dirs: {', '.join(dirs[:max_items])}{suffix}")
        if files:
            suffix = " ..." if len(files) > max_items else ""
            lines.append(f"Top-level files: {', '.join(files[:max_items])}{suffix}")
        if key_files:
            key_subset = [str(path) for path in key_files[:max_items]]
            suffix = " ..." if len(key_files) > max_items else ""
            lines.append(f"Key files: {', '.join(key_subset)}{suffix}")

        lines.append("Hint: use glob/grep/read to explore further.")
        return "\n".join(lines)

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
        chat_mode = data.get("chat_mode", False)
        system_prompt_override = data.get("system_prompt_override") # NEW: Get system prompt override

        if not task:
            return {"success": False, "error": "task required"}

        workspace_path = config.resolve_workspace_path(workspace)
        if not os.path.isdir(workspace_path):
            return {"success": False, "error": f"Workspace not found: {workspace}"}

        system_prompt = ""
        user_message_content = task

        if system_prompt_override: # NEW: If override is provided, use it
            system_prompt = system_prompt_override
            resolved_workspace = config.resolve_workspace_path(workspace)
            if resolved_workspace and "Resolved workspace path:" not in system_prompt:
                system_prompt += f"\nResolved workspace path: {resolved_workspace}"
            user_message = user_message_content # Raw user input
            print(f"[AGENT] Using system_prompt_override.")
            self._log_system_prompt_override(system_prompt)
        elif chat_mode and not task_id: # If in chat_mode and no specific task is active
            # Use minimal system prompt for chat
            system_prompt = self._minimal_chat_system_prompt()
            user_message = user_message_content # Raw user input for chat mode
            print(f"[AGENT] Chat Mode: Using minimal system prompt and raw user message.")
        else:
            # Existing logic for full task runs
            system_prompt = self._build_system_prompt(
                workspace=workspace,
                workspace_path=workspace_path,
                project_id=project_id,
                task_id=task_id
            )
            user_message = f"""Task: {user_message_content}

Workspace: {workspace}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Agent loop
        iteration = 0
        all_tool_calls = []
        result = {"success": False, "status": "INCOMPLETE", "summary": "Agent did not complete", "iterations": 0}
        start_time = time.time()

        def finalize_run(res: dict) -> dict:
            res.setdefault("iterations", iteration)
            res["tool_calls"] = res.get("tool_calls") or all_tool_calls
            res["duration_seconds"] = round(time.time() - start_time, 2)
            print(f"[AGENT] Run completed in {res['duration_seconds']}s with status {res.get('status')}")
            return res

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
            if isinstance(ollama_response, dict) and ollama_response.get("error"):
                result["error"] = ollama_response.get("error")
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
                tool_output = self._execute_agent_tool(tool_name, tool_args, workspace, task_id)

                all_tool_calls.append({
                    "iteration": iteration,
                    "tool": tool_name,
                    "args": tool_args,
                    "output": tool_output[:1000] if isinstance(tool_output, str) else str(tool_output)[:1000],
                })

                # Check for done signal
                if tool_name == "done":
                    done_status = tool_args.get("status", "PASS") # Use different variable names
                    done_summary = tool_args.get("summary", "Task completed")
                    if done_status == "PASS":
                        done_summary = self._clean_summary(done_summary)
                    
                    result = {
                        "success": done_status == "PASS",
                        "status": done_status,
                        "summary": done_summary,
                        "iterations": iteration,
                        "tool_calls": all_tool_calls,
                    }
                    return finalize_run(result) # Exit the whole agent loop if done is called

                # Append tool result for message history
                tool_results.append({
                    "role": "tool",
                    "content": json.dumps(tool_output) if isinstance(tool_output, dict) else str(tool_output),
                })
            
            # Add to message history after all tool calls in this iteration are processed
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

        return finalize_run(result)

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
            context = _ollama_ssl_context()
            with urllib.request.urlopen(req, timeout=120, context=context) as response:
                result = json.loads(response.read().decode("utf-8"))
                # Log which model actually responded
                if result.get("model"):
                    print(f"[AGENT] Response from model: {result.get('model')}")
                return result
        except urllib.error.HTTPError as exc:
            error_detail = self._extract_ollama_http_error(exc)
            print(f"[AGENT] Ollama error: HTTP {exc.code} {error_detail or ''}".strip())
            return {"error": error_detail or f"Ollama HTTP {exc.code}", "status_code": exc.code}
        except urllib.error.URLError as e:
            print(f"[AGENT] Ollama error: {e}")
            return {"error": f"Ollama error: {e}"}
        except Exception as e:
            print(f"[AGENT] Error: {e}")
            return {"error": f"Ollama error: {e}"}

    def _extract_ollama_http_error(self, exc) -> str:
        """Extract readable error message from Ollama HTTP errors."""
        try:
            raw = exc.read().decode("utf-8", errors="ignore").strip()
        except Exception:
            raw = ""
        if not raw:
            return ""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data.get("error") or raw
        except json.JSONDecodeError:
            return raw
        return raw

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

    def _execute_agent_tool(self, tool_name: str, args: dict, workspace: str, task_id: int = None) -> dict:
        """Execute a tool and return the result."""
        args["workspace"] = workspace

        if tool_name == "grep":
            return self._run_grep(args)
        elif tool_name == "glob":
            return self._run_glob(args)
        elif tool_name == "read":
            if "path" in args and isinstance(args["path"], str):
                workspace_path = config.resolve_workspace_path(workspace)
                args["path"] = self._normalize_path(workspace_path, args["path"])
            return self._run_read(args)
        elif tool_name == "bash":
            return self._run_bash(args)
        elif tool_name == "write":
            if "path" in args and isinstance(args["path"], str):
                workspace_path = config.resolve_workspace_path(workspace)
                args["path"] = self._normalize_path(workspace_path, args["path"])
            return self._run_write(args)
        elif tool_name == "edit":
            # Use aider for edits
            prompt = args.get("prompt", "")
            files = args.get("files", [])
            workspace_path = config.resolve_workspace_path(workspace)
            files = [
                self._normalize_path(workspace_path, f) for f in files
                if isinstance(f, str) and f.strip()
            ]
            return self._run_aider(workspace, prompt, files)
        elif tool_name == "done":
            # Done is handled in the main loop
            return {"status": args.get("status", "PASS"), "summary": args.get("summary", "")}
        elif tool_name == "delegate_subtask":
            return self._delegate_subtask(args, task_id)
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    def _delegate_subtask(self, args: dict, parent_task_id: int) -> dict:
        """Delegate a subtask to another agent via the main API.

        Creates a subtask through POST /tasks/{parent_id}/subtasks and optionally
        waits for it to complete.
        """
        import urllib.request
        import urllib.error

        if not parent_task_id:
            return {"success": False, "error": "Cannot delegate: no parent task context"}

        title = args.get("title", "").strip()
        description = args.get("description", "").strip()
        wait = args.get("wait", True)

        if not title or not description:
            return {"success": False, "error": "Both title and description are required"}

        # Main API URL (container-to-container communication)
        main_api_url = os.environ.get("MAIN_API_URL", "http://wfhub-v2-main-api:8002")

        # Create subtask via API
        subtask_payload = json.dumps({
            "title": title,
            "description": description,
        }).encode("utf-8")

        create_url = f"{main_api_url}/tasks/{parent_task_id}/subtasks"
        print(f"[DELEGATE] Creating subtask: {title} (parent={parent_task_id})")

        try:
            req = urllib.request.Request(
                create_url,
                data=subtask_payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                subtask = json.loads(response.read().decode("utf-8"))
                subtask_id = subtask.get("id")
                print(f"[DELEGATE] Created subtask {subtask_id}: {title}")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            print(f"[DELEGATE] Failed to create subtask: {e.code} - {error_body}")
            return {"success": False, "error": f"Failed to create subtask: {error_body}"}
        except Exception as e:
            print(f"[DELEGATE] Error creating subtask: {e}")
            return {"success": False, "error": f"Error creating subtask: {str(e)}"}

        if not wait:
            return {
                "success": True,
                "subtask_id": subtask_id,
                "status": "created",
                "message": f"Subtask '{title}' created (id={subtask_id}), running in background"
            }

        # Poll for completion
        poll_url = f"{main_api_url}/tasks/{subtask_id}"
        max_wait = 300  # 5 minutes
        poll_interval = 5  # seconds
        elapsed = 0

        print(f"[DELEGATE] Waiting for subtask {subtask_id} to complete...")
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                req = urllib.request.Request(poll_url)
                with urllib.request.urlopen(req, timeout=10) as response:
                    task_status = json.loads(response.read().decode("utf-8"))
                    status = task_status.get("status")

                    if status in ("completed", "failed"):
                        print(f"[DELEGATE] Subtask {subtask_id} finished with status: {status}")

                        # Get the task run result if available
                        result_summary = task_status.get("result", {}).get("summary", "")
                        return {
                            "success": status == "completed",
                            "subtask_id": subtask_id,
                            "status": status,
                            "title": title,
                            "result": result_summary or f"Subtask {status}",
                        }

                    print(f"[DELEGATE] Subtask {subtask_id} status: {status} (waited {elapsed}s)")

            except Exception as e:
                print(f"[DELEGATE] Error polling subtask: {e}")
                # Continue polling on transient errors

        # Timeout
        return {
            "success": False,
            "subtask_id": subtask_id,
            "status": "timeout",
            "error": f"Subtask did not complete within {max_wait}s"
        }

    def log_message(self, format, *args):
        # Skip logging health checks to reduce noise
        if args and "/health" in str(args[0]):
            return
        print(f"[AIDER-API] {args[0]}")


def main():
    port = int(os.environ.get("PORT", 8001))
    server = ThreadingHTTPServer(("0.0.0.0", port), AiderAPIHandler)
    print(f"[AIDER-API] Starting on port {port}")
    print(f"[AIDER-API] Aider Model: {config.aider_model}")
    print(f"[AIDER-API] Agent Model: {config.agent_model}")
    print(f"[AIDER-API] Ollama: {config.ollama_api_base}")
    print(f"[AIDER-API] Workspaces: {config.workspaces_dir}")
    print(f"[AIDER-API] Default Workspace: {config.current_workspace}")
    server.serve_forever()


if __name__ == "__main__":
    main()
