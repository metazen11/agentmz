"""Tests for the Coding Agent API (aider_api.py).

Run with: pytest v2/tests/test_aider_api.py -v
Requires: aider_api.py running on localhost:8001
"""

import json
import os
import pytest
import urllib.request
import urllib.error

# API base URL - can be overridden by environment
API_URL = os.environ.get("AIDER_API_URL", "http://localhost:8001")


def api_get(path: str) -> dict:
    """Make a GET request to the API."""
    url = f"{API_URL}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        pytest.fail(f"API request failed: {e}")


def api_post(path: str, data: dict) -> dict:
    """Make a POST request to the API."""
    url = f"{API_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Return error response body as JSON
        return json.loads(e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        pytest.fail(f"API request failed: {e}")


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_returns_ok(self):
        """Health endpoint should return status ok."""
        result = api_get("/health")
        assert result["status"] == "ok"

    def test_health_includes_models(self):
        """Health endpoint should include model configuration."""
        result = api_get("/health")
        assert "aider_model" in result
        assert "agent_model" in result
        assert "max_iterations" in result
        assert "ollama_url" in result

    def test_health_includes_workspace(self):
        """Health endpoint should include current workspace."""
        result = api_get("/health")
        assert "current_workspace" in result


class TestConfigEndpoint:
    """Tests for /api/config endpoint."""

    def test_get_config(self):
        """GET /api/config should return full configuration."""
        result = api_get("/api/config")
        assert result["success"] is True
        assert "config" in result
        assert "workspaces" in result

        config = result["config"]
        assert "ollama_api_base" in config
        assert "aider_model" in config
        assert "agent_model" in config
        assert "workspaces_dir" in config
        assert "current_workspace" in config

    def test_list_workspaces(self):
        """Config should list available workspaces."""
        result = api_get("/api/config")
        assert isinstance(result["workspaces"], list)
        # poc workspace should exist
        assert "poc" in result["workspaces"]

    def test_switch_workspace(self):
        """POST /api/config should allow switching workspace."""
        # Switch to poc workspace
        result = api_post("/api/config", {"workspace": "poc"})
        assert result["success"] is True
        assert result["current_workspace"] == "poc"

    def test_switch_invalid_workspace(self):
        """Switching to invalid workspace should fail."""
        result = api_post("/api/config", {"workspace": "nonexistent_workspace_xyz"})
        assert result["success"] is False
        assert "error" in result

    def test_switch_workspace_affects_tools(self):
        """Switching workspace should affect subsequent tool calls."""
        # Get current workspace
        config = api_get("/api/config")
        original_workspace = config["config"]["current_workspace"]

        # Find another workspace to switch to
        workspaces = config["workspaces"]
        other_workspace = None
        for ws in workspaces:
            if ws != original_workspace and ws != ".git":
                other_workspace = ws
                break

        if not other_workspace:
            pytest.skip("No other workspace available to test switching")

        # Switch to other workspace
        result = api_post("/api/config", {"workspace": other_workspace})
        assert result["success"] is True
        assert result["current_workspace"] == other_workspace

        # Verify health shows new workspace
        health = api_get("/health")
        assert health["current_workspace"] == other_workspace

        # Glob should work in new workspace (no explicit workspace param)
        glob_result = api_post("/api/glob", {"pattern": "*"})
        assert glob_result["success"] is True

        # Switch back to original
        api_post("/api/config", {"workspace": original_workspace})
        health = api_get("/health")
        assert health["current_workspace"] == original_workspace

    def test_update_agent_model(self):
        """Should be able to update agent model at runtime."""
        # Get current model
        config = api_get("/api/config")
        original_model = config["config"]["agent_model"]

        # Update model
        result = api_post("/api/config", {"agent_model": "test-model:latest"})
        assert result["success"] is True
        assert result["agent_model"] == "test-model:latest"

        # Verify change
        health = api_get("/health")
        assert health["agent_model"] == "test-model:latest"

        # Restore original
        api_post("/api/config", {"agent_model": original_model})

    def test_update_max_iterations(self):
        """Should be able to update max_iterations at runtime."""
        # Get current value
        config = api_get("/api/config")
        original_max = config["config"]["max_iterations"]

        # Update
        result = api_post("/api/config", {"max_iterations": 10})
        assert result["success"] is True
        assert result["max_iterations"] == 10

        # Verify
        health = api_get("/health")
        assert health["max_iterations"] == 10

        # Restore
        api_post("/api/config", {"max_iterations": original_max})


class TestGrepEndpoint:
    """Tests for POST /api/grep endpoint."""

    def test_grep_requires_pattern(self):
        """Grep should require a pattern."""
        result = api_post("/api/grep", {})
        assert result["success"] is False
        assert "pattern" in result["error"].lower()

    def test_grep_finds_matches(self):
        """Grep should find matches in files."""
        # Search for 'html' in the poc workspace (index.html exists)
        result = api_post("/api/grep", {
            "pattern": "html",
            "workspace": "poc",
        })
        assert result["success"] is True
        assert "matches" in result
        assert "count" in result
        assert result["count"] > 0

    def test_grep_with_glob_filter(self):
        """Grep should support file pattern filtering."""
        result = api_post("/api/grep", {
            "pattern": "def|function",
            "workspace": "poc",
            "glob": "*.py",
        })
        assert result["success"] is True
        # Should only search .py files
        for match in result.get("matches", []):
            assert match["file"].endswith(".py") or ".py" in match["file"]

    def test_grep_case_insensitive(self):
        """Grep should support case insensitive search."""
        result = api_post("/api/grep", {
            "pattern": "HTML",
            "workspace": "poc",
            "case_insensitive": True,
        })
        assert result["success"] is True

    def test_grep_invalid_workspace(self):
        """Grep should fail for invalid workspace."""
        result = api_post("/api/grep", {
            "pattern": "test",
            "workspace": "nonexistent_xyz",
        })
        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestGlobEndpoint:
    """Tests for POST /api/glob endpoint."""

    def test_glob_requires_pattern(self):
        """Glob should require a pattern."""
        result = api_post("/api/glob", {})
        assert result["success"] is False
        assert "pattern" in result["error"].lower()

    def test_glob_finds_files(self):
        """Glob should find files matching pattern."""
        result = api_post("/api/glob", {
            "pattern": "*.html",
            "workspace": "poc",
        })
        assert result["success"] is True
        assert "files" in result
        assert "count" in result
        assert result["count"] > 0
        # Should find index.html
        assert any("html" in f for f in result["files"])

    def test_glob_recursive(self):
        """Glob should support recursive patterns."""
        result = api_post("/api/glob", {
            "pattern": "**/*.py",
            "workspace": "poc",
        })
        assert result["success"] is True
        assert "files" in result

    def test_glob_returns_relative_paths(self):
        """Glob should return paths relative to workspace."""
        result = api_post("/api/glob", {
            "pattern": "*",
            "workspace": "poc",
        })
        assert result["success"] is True
        # Paths should be relative (not absolute)
        for f in result.get("files", []):
            assert not f.startswith("/")


class TestReadEndpoint:
    """Tests for POST /api/read endpoint."""

    def test_read_requires_path(self):
        """Read should require a path."""
        result = api_post("/api/read", {})
        assert result["success"] is False
        assert "path" in result["error"].lower()

    def test_read_file_contents(self):
        """Read should return file contents."""
        result = api_post("/api/read", {
            "path": "index.html",
            "workspace": "poc",
        })
        assert result["success"] is True
        assert "content" in result
        assert "lines" in result
        assert "total_lines" in result
        assert len(result["content"]) > 0

    def test_read_with_offset(self):
        """Read should support line offset."""
        # Read all lines first
        full = api_post("/api/read", {"path": "index.html", "workspace": "poc"})

        # Read from line 5
        partial = api_post("/api/read", {
            "path": "index.html",
            "workspace": "poc",
            "offset": 5,
        })

        assert partial["success"] is True
        assert partial["lines"] < full["lines"]

    def test_read_with_limit(self):
        """Read should support line limit."""
        result = api_post("/api/read", {
            "path": "index.html",
            "workspace": "poc",
            "limit": 5,
        })
        assert result["success"] is True
        assert result["lines"] <= 5

    def test_read_nonexistent_file(self):
        """Read should fail for nonexistent file."""
        result = api_post("/api/read", {
            "path": "nonexistent_file_xyz.txt",
            "workspace": "poc",
        })
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_read_path_traversal_blocked(self):
        """Read should block path traversal attempts."""
        result = api_post("/api/read", {
            "path": "../../../etc/passwd",
            "workspace": "poc",
        })
        assert result["success"] is False
        # Should be blocked either by "outside workspace" or "not found"
        assert "denied" in result["error"].lower() or "not found" in result["error"].lower()


class TestBashEndpoint:
    """Tests for POST /api/bash endpoint."""

    def test_bash_requires_command(self):
        """Bash should require a command."""
        result = api_post("/api/bash", {})
        assert result["success"] is False
        assert "command" in result["error"].lower()

    def test_bash_runs_command(self):
        """Bash should execute commands."""
        result = api_post("/api/bash", {
            "command": "echo 'hello world'",
            "workspace": "poc",
        })
        assert result["success"] is True
        assert "stdout" in result
        assert "hello world" in result["stdout"]

    def test_bash_returns_exit_code(self):
        """Bash should return exit code."""
        result = api_post("/api/bash", {
            "command": "exit 0",
            "workspace": "poc",
        })
        assert "returncode" in result
        assert result["returncode"] == 0

    def test_bash_captures_failure(self):
        """Bash should capture failed commands."""
        result = api_post("/api/bash", {
            "command": "exit 1",
            "workspace": "poc",
        })
        assert result["success"] is False
        assert result["returncode"] == 1

    def test_bash_runs_in_workspace(self):
        """Bash should run in the workspace directory."""
        result = api_post("/api/bash", {
            "command": "ls index.html",
            "workspace": "poc",
        })
        assert result["success"] is True
        assert "index.html" in result["stdout"]

    def test_bash_blocks_dangerous_commands(self):
        """Bash should block dangerous commands."""
        result = api_post("/api/bash", {
            "command": "rm -rf /",
            "workspace": "poc",
        })
        assert result["success"] is False
        assert "blocked" in result["error"].lower()

    def test_bash_respects_timeout(self):
        """Bash should respect timeout."""
        result = api_post("/api/bash", {
            "command": "sleep 1 && echo done",
            "workspace": "poc",
            "timeout": 5,
        })
        assert result["success"] is True
        assert "done" in result["stdout"]


class TestAiderExecuteEndpoint:
    """Tests for POST /api/aider/execute endpoint.

    Note: These tests require Ollama running with the configured model.
    Skip if Ollama is not available.
    """

    @pytest.fixture(autouse=True)
    def check_ollama(self):
        """Skip tests if Ollama is not available."""
        try:
            result = api_get("/health")
            # Check if we can reach Ollama
            import urllib.request
            ollama_url = result.get("ollama_url", "http://localhost:11434")
            req = urllib.request.Request(f"{ollama_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pytest.skip("Ollama not available")

    def test_aider_requires_prompt(self):
        """Aider should require a prompt."""
        result = api_post("/api/aider/execute", {})
        assert "error" in result
        assert "prompt" in result["error"].lower()


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
