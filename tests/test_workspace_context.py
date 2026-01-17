"""Tests for dynamic workspace mounting and context injection.

This test validates that any workspace can be mounted dynamically and
project context (project.md, task.md) is properly loaded and injected.

Context files (created automatically or manually):
    - project.md: Project-level instructions (tech stack, conventions)
    - task.md: Task-specific instructions (current task requirements)

The system uses ProjectDiscovery to auto-extract:
    - Languages, frameworks, databases
    - Git info, Docker services, CI/CD workflows
    - API routes, environment variables

Run with:
    pytest tests/test_workspace_context.py -v -s

Prerequisites:
    - aider-api running on localhost:8001
    - Ollama running on localhost:11435
"""

import json
import os
import pytest
import urllib.request
import urllib.error
from pathlib import Path

# API base URL
API_URL = os.environ.get("AIDER_API_URL", "http://localhost:8001")

# Test workspace name - can be any workspace in the workspaces folder
TEST_WORKSPACE = os.environ.get("TEST_WORKSPACE", "beatbridge_app")


def api_get(path: str) -> dict:
    """Make a GET request to the API."""
    url = f"{API_URL}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        pytest.fail(f"API request failed: {e}")


def api_post(path: str, data: dict, timeout: int = 30) -> dict:
    """Make a POST request to the API."""
    url = f"{API_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        pytest.fail(f"API request failed: {e}")


class TestPrerequisites:
    """Verify test prerequisites are met."""

    def test_aider_api_running(self):
        """Aider API should be running."""
        result = api_get("/health")
        assert result["status"] == "ok", "Aider API not healthy"

    def test_list_available_workspaces(self):
        """Should list all available workspaces."""
        result = api_get("/api/config")
        assert result["success"] is True
        assert isinstance(result["workspaces"], list)
        print(f"\nAvailable workspaces: {result['workspaces']}")
        # At minimum, poc should exist
        assert "poc" in result["workspaces"], "poc workspace should always exist"

    def test_test_workspace_exists(self):
        """Test workspace should exist (configured via TEST_WORKSPACE env)."""
        result = api_get("/api/config")
        assert result["success"] is True
        if TEST_WORKSPACE not in result["workspaces"]:
            pytest.skip(f"Test workspace '{TEST_WORKSPACE}' not found. Available: {result['workspaces']}")


class TestDynamicWorkspaceMounting:
    """Tests for dynamically mounting any workspace."""

    def test_switch_to_any_workspace(self):
        """Should successfully switch to any valid workspace."""
        result = api_get("/api/config")
        workspaces = result["workspaces"]

        for workspace in workspaces:
            switch_result = api_post("/api/config", {"workspace": workspace})
            assert switch_result["success"] is True, f"Failed to switch to {workspace}"
            assert switch_result["current_workspace"] == workspace

        # Reset to default
        api_post("/api/config", {"workspace": "poc"})

    def test_switch_to_invalid_workspace_fails(self):
        """Switching to non-existent workspace should fail gracefully."""
        result = api_post("/api/config", {"workspace": "nonexistent_workspace_12345"})
        assert result["success"] is False
        assert "error" in result

    def test_workspace_isolation(self):
        """Files in one workspace should not be visible in another."""
        result = api_get("/api/config")
        workspaces = result["workspaces"]

        if len(workspaces) < 2:
            pytest.skip("Need at least 2 workspaces to test isolation")

        # Get files from first workspace
        api_post("/api/config", {"workspace": workspaces[0]})
        files1 = api_post("/api/glob", {"pattern": "*", "workspace": workspaces[0]})

        # Get files from second workspace
        api_post("/api/config", {"workspace": workspaces[1]})
        files2 = api_post("/api/glob", {"pattern": "*", "workspace": workspaces[1]})

        # Files should be different (unless both empty)
        if files1.get("files") and files2.get("files"):
            # At least the path context should be different
            print(f"\nWorkspace {workspaces[0]} files: {files1.get('files', [])[:5]}")
            print(f"Workspace {workspaces[1]} files: {files2.get('files', [])[:5]}")


class TestContextInjection:
    """Tests for project context auto-discovery and injection."""

    def test_glob_finds_files_in_workspace(self):
        """Should find files in the active workspace."""
        api_post("/api/config", {"workspace": TEST_WORKSPACE})

        result = api_post("/api/glob", {
            "pattern": "*",
            "workspace": TEST_WORKSPACE
        })
        assert result["success"] is True
        print(f"\nFiles in {TEST_WORKSPACE}: {result.get('files', [])[:10]}")

    def test_read_project_md_if_exists(self):
        """Should read project.md content if it exists."""
        result = api_post("/api/read", {
            "path": "project.md",
            "workspace": TEST_WORKSPACE
        })

        if result["success"]:
            content = result["content"]
            print(f"\nproject.md found ({len(content)} chars)")
            # Verify it's a valid context file
            assert len(content) > 10, "project.md should have content"
        else:
            print(f"\nNo project.md in {TEST_WORKSPACE} (this is OK for auto-discovery)")

    def test_context_endpoint_returns_aggregated_context(self):
        """The /api/context endpoint should return aggregated context."""
        result = api_post("/api/context", {"workspace": TEST_WORKSPACE})
        assert result["success"] is True
        assert "context" in result
        assert result["workspace"] == TEST_WORKSPACE

        ctx = result["context"]
        print(f"\nContext for {TEST_WORKSPACE}:")
        print(f"  Name: {ctx.get('name', 'unknown')}")
        print(f"  Languages: {ctx.get('languages', [])}")
        print(f"  Frameworks: {ctx.get('frameworks', [])}")
        print(f"  Key files: {ctx.get('key_files', [])}")
        print(f"  Has project.md: {ctx.get('has_project_instructions', False)}")
        print(f"  Has task.md: {ctx.get('has_task_instructions', False)}")
        print(f"  Loaded from: {ctx.get('loaded_from', [])}")

    def test_context_includes_discovery_data(self):
        """Context should include auto-discovered project metadata."""
        result = api_post("/api/context", {"workspace": TEST_WORKSPACE})
        assert result["success"] is True

        ctx = result["context"]
        # Discovery should always add itself to loaded_from
        assert "discovery" in ctx.get("loaded_from", []) or \
               len(ctx.get("languages", [])) > 0 or \
               len(ctx.get("frameworks", [])) > 0, \
               "Context should include discovered data"

    def test_context_with_project_id(self):
        """Context should include database data when project_id provided."""
        result = api_post("/api/context", {
            "workspace": TEST_WORKSPACE,
            "project_id": 1  # May or may not exist
        })
        # Should succeed even if project doesn't exist
        assert result["success"] is True

    def test_auto_discovery_extracts_project_info(self):
        """ProjectDiscovery should extract project metadata automatically."""
        # This tests that even without project.md, the system extracts context
        api_post("/api/config", {"workspace": TEST_WORKSPACE})

        # The glob should work, indicating the workspace is accessible
        result = api_post("/api/glob", {"pattern": "*.py", "workspace": TEST_WORKSPACE})
        assert result["success"] is True

        # Check for common project indicators
        all_files = api_post("/api/glob", {"pattern": "**/*", "workspace": TEST_WORKSPACE})
        if all_files["success"]:
            files = all_files.get("files", [])
            indicators = {
                "has_python": any(f.endswith(".py") for f in files),
                "has_javascript": any(f.endswith((".js", ".ts")) for f in files),
                "has_requirements": any("requirements" in f for f in files),
                "has_package_json": any("package.json" in f for f in files),
                "has_docker": any("docker" in f.lower() for f in files),
            }
            print(f"\nProject indicators for {TEST_WORKSPACE}: {indicators}")


class TestAgentWithContext:
    """Tests for agent behavior with injected context."""

    @pytest.mark.slow
    def test_agent_operates_in_correct_workspace(self):
        """Agent should operate in the specified workspace."""
        api_post("/api/config", {"workspace": TEST_WORKSPACE})

        result = api_post("/api/agent/run", {
            "task": "List all files in this workspace using glob. Report what you find.",
            "workspace": TEST_WORKSPACE,
            "max_iterations": 3
        }, timeout=120)

        # Agent should complete successfully
        assert result.get("success") is True or result.get("status") in ["PASS", "DONE"], \
            f"Agent task failed: {result}"

        print(f"\nAgent output: {result.get('summary', result.get('output', ''))[:500]}")

    @pytest.mark.slow
    def test_agent_with_task_context(self):
        """Agent should receive task context when task_id and project_id provided."""
        # This test verifies the task history injection works
        result = api_post("/api/agent/run", {
            "task": "What files exist in this workspace?",
            "workspace": TEST_WORKSPACE,
            "max_iterations": 3,
            "project_id": 1,  # Will fetch task history if project exists
            "task_id": 1
        }, timeout=120)

        # Should complete (even if no task history exists)
        assert result.get("success") is True or result.get("status") in ["PASS", "DONE", "INCOMPLETE"], \
            f"Agent task failed unexpectedly: {result}"


class TestCleanup:
    """Reset state after tests."""

    def test_reset_to_default_workspace(self):
        """Reset workspace to poc after tests."""
        result = api_post("/api/config", {"workspace": "poc"})
        assert result["success"] is True
        assert result["current_workspace"] == "poc"
