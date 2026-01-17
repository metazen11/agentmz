"""Test chat interface functionality with both APIs."""
import os
import pytest
import requests

MAIN_API = os.getenv("MAIN_API_URL", "http://localhost:8002")
AIDER_API = os.getenv("AIDER_API_URL", "http://localhost:8001")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))


class TestChatInterfaceAPIs:
    """Verify APIs that the chat interface uses."""
    @staticmethod
    def _get_test_project():
        res = requests.get(f"{MAIN_API}/projects", timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return next(p for p in res.json() if p["name"] == "chat-test-project")

    @staticmethod
    def _create_task(project_id: int, title: str, description: str = ""):
        res = requests.post(
            f"{MAIN_API}/tasks",
            json={
                "project_id": project_id,
                "title": title,
                "description": description,
            },
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
        return res.json()

    def test_main_api_health(self):
        """Main API should respond."""
        res = requests.get(f"{MAIN_API}/projects", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_aider_api_health(self):
        """Aider API should respond."""
        res = requests.get(f"{AIDER_API}/health", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        data = res.json()
        assert "status" in data

    def test_create_project(self):
        """Create a project via API."""
        res = requests.post(
            f"{MAIN_API}/projects",
            json={
                "name": "chat-test-project",
                "workspace_path": "/workspaces/poc",
                "environment": "local",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "chat-test-project"
        assert "id" in data

    def test_list_projects(self):
        """List projects should include created project."""
        res = requests.get(f"{MAIN_API}/projects", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        projects = res.json()
        assert len(projects) > 0
        assert any(p["name"] == "chat-test-project" for p in projects)

    def test_update_project(self):
        """Update project metadata."""
        project = self._get_test_project()
        res = requests.patch(
            f"{MAIN_API}/projects/{project['id']}",
            json={"environment": "local-updated"},
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == project["id"]
        assert data["environment"] == "local-updated"

    def test_delete_project(self):
        """Delete a project."""
        res = requests.post(
            f"{MAIN_API}/projects",
            json={
                "name": "chat-delete-project",
                "workspace_path": "/workspaces/poc",
                "environment": "local",
            },
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
        project_id = res.json()["id"]

        res = requests.delete(
            f"{MAIN_API}/projects/{project_id}",
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["deleted"] is True

    def test_create_task(self):
        """Create task for project."""
        project = self._get_test_project()
        data = self._create_task(
            project["id"],
            "Test task from chat",
            "This is a test task",
        )
        assert data["title"] == "Test task from chat"
        assert data["status"] == "backlog"

    def test_list_project_tasks(self):
        """List tasks for project."""
        project = self._get_test_project()
        res = requests.get(
            f"{MAIN_API}/projects/{project['id']}/tasks",
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        tasks = res.json()
        assert len(tasks) > 0
        assert any(t["title"] == "Test task from chat" for t in tasks)

    def test_update_task(self):
        """Update task title/description/status/stage."""
        project = self._get_test_project()
        task = self._create_task(project["id"], "Task to update", "Original description")
        res = requests.patch(
            f"{MAIN_API}/tasks/{task['id']}",
            json={
                "title": "Task updated",
                "description": "Updated description",
                "status": "in_progress",
                "stage": "qa",
            },
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Task updated"
        assert data["description"] == "Updated description"
        assert data["status"] == "in_progress"
        assert data["stage"] == "qa"

    def test_delete_task(self):
        """Delete a task."""
        project = self._get_test_project()
        task = self._create_task(project["id"], "Task to delete", "To be removed")
        res = requests.delete(
            f"{MAIN_API}/tasks/{task['id']}",
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["deleted"] is True

    def test_switch_workspace(self):
        """Switch aider workspace via API."""
        res = requests.post(
            f"{AIDER_API}/api/config",
            json={"workspace": "poc"},
            timeout=REQUEST_TIMEOUT,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

    def test_aider_execute(self):
        """Execute aider command (may timeout with slow LLM)."""
        try:
            res = requests.post(
                f"{AIDER_API}/api/aider/execute",
                json={
                    "workspace": "poc",
                    "prompt": "list the files in this directory",
                    "files": [],
                },
                timeout=120,  # LLM inference can be slow
            )
            assert res.status_code == 200
            data = res.json()
            # Just check response structure, not success (LLM might fail)
            assert "success" in data
        except requests.exceptions.ReadTimeout:
            # LLM timeout is acceptable - the endpoint works
            pytest.skip("LLM inference timed out (expected with slow models)")

    def test_logs_endpoint_ollama(self):
        """Get ollama container logs."""
        res = requests.get(f"{MAIN_API}/logs/ollama?lines=10", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        data = res.json()
        assert data["container"] == "wfhub-v2-ollama"
        assert "logs" in data

    def test_logs_endpoint_aider(self):
        """Get aider container logs."""
        res = requests.get(f"{MAIN_API}/logs/aider?lines=10", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        data = res.json()
        assert data["container"] == "wfhub-v2-aider-api"
        assert "logs" in data

    def test_logs_endpoint_ollama_http(self):
        """Get Ollama HTTP proxy logs."""
        res = requests.get(f"{MAIN_API}/logs/ollama_http?lines=10", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        data = res.json()
        assert data["container"] == "ollama_http"
        assert "logs" in data

    def test_logs_endpoint_invalid(self):
        """Invalid container returns 404."""
        res = requests.get(f"{MAIN_API}/logs/invalid", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 404

    def test_full_health_endpoint(self):
        """Full health endpoint should return overall status."""
        res = requests.get(f"{MAIN_API}/health/full", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 200
        data = res.json()
        assert data["overall_status"] in {"ok", "degraded"}
        assert "database" in data
        assert "aider_api" in data

    def test_restart_invalid_service(self):
        """Restart endpoint should reject unsupported service."""
        res = requests.post(f"{MAIN_API}/ops/restart/invalid", timeout=REQUEST_TIMEOUT)
        assert res.status_code == 404

    def test_cleanup(self):
        """Clean up test project."""
        res = requests.get(f"{MAIN_API}/projects", timeout=REQUEST_TIMEOUT)
        projects = res.json()
        test_projects = [p for p in projects if p["name"] == "chat-test-project"]
        for p in test_projects:
            requests.delete(f"{MAIN_API}/projects/{p['id']}", timeout=REQUEST_TIMEOUT)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
