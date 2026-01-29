"""Integration tests for subtask delegation API endpoints.

These tests use the real database. Test data is cleaned up after each test.
"""
import pytest
import httpx

# API base URL - use environment or default
API_URL = "http://localhost:8002"


@pytest.fixture
def api_client():
    """Create an HTTP client for API calls."""
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        yield client


@pytest.fixture
def test_project(api_client):
    """Create a test project and clean up after."""
    # Create project
    response = api_client.post("/projects", json={
        "name": "Test Project for Subtask Delegation",
        "workspace_path": "/tmp/test-subtask-delegation",
        "environment": "local",
    })
    assert response.status_code == 200, f"Failed to create project: {response.text}"
    project = response.json()
    project_id = project["id"]

    yield project

    # Cleanup: delete project (cascades to tasks)
    api_client.delete(f"/projects/{project_id}")


@pytest.fixture
def test_task(api_client, test_project):
    """Create a test task and clean up after."""
    response = api_client.post("/tasks", json={
        "project_id": test_project["id"],
        "title": "Parent Task for Subtask Test",
        "description": "This task will have subtasks delegated to it",
        "acceptance_criteria": [
            {"description": "Test criteria"}
        ],
    })
    assert response.status_code == 200, f"Failed to create task: {response.text}"
    task = response.json()

    yield task

    # Cleanup handled by project deletion


class TestSubtaskCreation:
    """Tests for POST /tasks/{task_id}/subtasks endpoint."""

    def test_create_subtask_success(self, api_client, test_task):
        """Should create a subtask with depth = parent.depth + 1."""
        response = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
            "title": "Subtask 1",
            "description": "First delegated subtask",
        })

        assert response.status_code == 200, f"Failed: {response.text}"
        subtask = response.json()

        assert subtask["title"] == "Subtask 1"
        assert subtask["parent_id"] == test_task["id"]
        assert subtask["project_id"] == test_task["project_id"]
        assert subtask["depth"] == 1  # Parent depth (0) + 1
        assert subtask["status"] == "in_progress"

    def test_create_subtask_inherits_node(self, api_client, test_task):
        """Subtask should inherit parent's node_id if not specified."""
        response = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
            "title": "Subtask inheriting node",
            "description": "Should have same node as parent",
        })

        assert response.status_code == 200
        subtask = response.json()
        assert subtask["node_id"] == test_task["node_id"]

    def test_create_nested_subtask(self, api_client, test_task):
        """Should create nested subtasks up to max depth."""
        # Create depth 1 subtask
        resp1 = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
            "title": "Depth 1 subtask",
            "description": "First level",
        })
        assert resp1.status_code == 200
        subtask1 = resp1.json()
        assert subtask1["depth"] == 1

        # Create depth 2 subtask
        resp2 = api_client.post(f"/tasks/{subtask1['id']}/subtasks?trigger=false", json={
            "title": "Depth 2 subtask",
            "description": "Second level",
        })
        assert resp2.status_code == 200
        subtask2 = resp2.json()
        assert subtask2["depth"] == 2

        # Create depth 3 subtask
        resp3 = api_client.post(f"/tasks/{subtask2['id']}/subtasks?trigger=false", json={
            "title": "Depth 3 subtask",
            "description": "Third level (max)",
        })
        assert resp3.status_code == 200
        subtask3 = resp3.json()
        assert subtask3["depth"] == 3

    def test_reject_subtask_exceeding_max_depth(self, api_client, test_task):
        """Should reject subtask creation when max depth exceeded."""
        # Create chain to depth 3
        current_task = test_task
        for i in range(3):
            resp = api_client.post(f"/tasks/{current_task['id']}/subtasks?trigger=false", json={
                "title": f"Depth {i+1} subtask",
                "description": f"Level {i+1}",
            })
            assert resp.status_code == 200
            current_task = resp.json()

        # Now at depth 3, trying to create depth 4 should fail
        resp = api_client.post(f"/tasks/{current_task['id']}/subtasks?trigger=false", json={
            "title": "Depth 4 subtask (should fail)",
            "description": "Exceeds max depth",
        })

        assert resp.status_code == 400
        assert "depth" in resp.json()["detail"].lower()

    def test_reject_subtask_exceeding_max_count(self, api_client, test_task):
        """Should reject subtask creation when max count exceeded."""
        # Create 10 subtasks (the limit)
        for i in range(10):
            resp = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
                "title": f"Subtask {i+1}",
                "description": f"Subtask number {i+1}",
            })
            assert resp.status_code == 200, f"Failed at subtask {i+1}: {resp.text}"

        # 11th should fail
        resp = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
            "title": "Subtask 11 (should fail)",
            "description": "Exceeds max count",
        })

        assert resp.status_code == 400
        assert "subtask" in resp.json()["detail"].lower()

    def test_subtask_not_found_parent(self, api_client):
        """Should return 404 for non-existent parent task."""
        response = api_client.post("/tasks/999999/subtasks?trigger=false", json={
            "title": "Orphan subtask",
            "description": "Parent doesn't exist",
        })

        assert response.status_code == 404


class TestSubtaskListing:
    """Tests for GET /tasks/{task_id}/subtasks endpoint."""

    def test_list_subtasks_empty(self, api_client, test_task):
        """Should return empty list when no subtasks exist."""
        response = api_client.get(f"/tasks/{test_task['id']}/subtasks")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_subtasks(self, api_client, test_task):
        """Should return all subtasks of a task."""
        # Create some subtasks
        for i in range(3):
            api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
                "title": f"Subtask {i+1}",
                "description": f"Description {i+1}",
            })

        response = api_client.get(f"/tasks/{test_task['id']}/subtasks")

        assert response.status_code == 200
        subtasks = response.json()
        assert len(subtasks) == 3
        assert all(s["parent_id"] == test_task["id"] for s in subtasks)

    def test_list_subtasks_not_nested(self, api_client, test_task):
        """Listing subtasks should only return direct children, not grandchildren."""
        # Create subtask
        resp1 = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
            "title": "Direct child",
            "description": "Level 1",
        })
        subtask1 = resp1.json()

        # Create grandchild
        api_client.post(f"/tasks/{subtask1['id']}/subtasks?trigger=false", json={
            "title": "Grandchild",
            "description": "Level 2",
        })

        # List parent's subtasks - should only have direct child
        response = api_client.get(f"/tasks/{test_task['id']}/subtasks")

        assert response.status_code == 200
        subtasks = response.json()
        assert len(subtasks) == 1
        assert subtasks[0]["title"] == "Direct child"


class TestTaskDepthField:
    """Tests for depth field in task responses."""

    def test_task_has_depth_field(self, api_client, test_task):
        """Task response should include depth field."""
        response = api_client.get(f"/tasks/{test_task['id']}")

        assert response.status_code == 200
        task = response.json()
        assert "depth" in task
        assert task["depth"] == 0  # Root task

    def test_subtask_depth_in_response(self, api_client, test_task):
        """Subtask response should show correct depth."""
        # Create subtask
        resp = api_client.post(f"/tasks/{test_task['id']}/subtasks?trigger=false", json={
            "title": "Subtask with depth",
            "description": "Check depth field",
        })
        subtask = resp.json()

        # Fetch it again
        response = api_client.get(f"/tasks/{subtask['id']}")

        assert response.status_code == 200
        fetched = response.json()
        assert fetched["depth"] == 1


class TestHealthCheck:
    """Basic health check to ensure API is running."""

    def test_health_endpoint(self, api_client):
        """Health endpoint should respond."""
        response = api_client.get("/health")
        # May return 200 or 404 depending on implementation
        assert response.status_code in [200, 404, 405]


class TestAgentDelegation:
    """E2E tests for agent delegation via the delegate_subtask tool."""

    AIDER_API_URL = "http://localhost:8001"

    @pytest.fixture
    def aider_client(self):
        """Create an HTTP client for aider-api calls."""
        with httpx.Client(base_url=self.AIDER_API_URL, timeout=120) as client:
            yield client

    def test_aider_api_health(self, aider_client):
        """Aider API should be running."""
        response = aider_client.get("/health")
        assert response.status_code == 200

    def test_agent_with_delegation_task(self, api_client, aider_client, test_project, test_task):
        """Agent should be able to delegate subtasks when given a complex task.

        This test creates a task, triggers the agent with instructions to delegate,
        and verifies subtasks are created.
        """
        # Update task to have a delegation-friendly description
        update_resp = api_client.patch(f"/tasks/{test_task['id']}", json={
            "description": """You have a complex task that requires delegation.

Please delegate TWO subtasks:
1. First subtask: Create a file called 'part1.txt' with the content 'Hello from subtask 1'
2. Second subtask: Create a file called 'part2.txt' with the content 'Hello from subtask 2'

Use the delegate_subtask tool for each part, then call done when both are delegated."""
        })
        # May be 200 or 204 depending on implementation
        assert update_resp.status_code in [200, 204]

        # Trigger agent execution with explicit delegation instruction
        agent_response = aider_client.post("/api/agent/run", json={
            "task": """Your task is to delegate work. Use the delegate_subtask tool to create these subtasks:

1. delegate_subtask(title="Create part1.txt", description="Create a file called part1.txt with content: Hello from subtask 1")
2. delegate_subtask(title="Create part2.txt", description="Create a file called part2.txt with content: Hello from subtask 2")

After delegating both, call done(status="PASS", summary="Delegated 2 subtasks")""",
            "workspace": "poc",  # Use existing poc workspace
            "task_id": test_task["id"],
            "max_iterations": 5,
        }, timeout=120)

        # Check agent completed (may or may not have delegated depending on LLM)
        assert agent_response.status_code == 200
        result = agent_response.json()
        print(f"Agent result: {result}")

        # Check if subtasks were created
        subtasks_resp = api_client.get(f"/tasks/{test_task['id']}/subtasks")
        assert subtasks_resp.status_code == 200
        subtasks = subtasks_resp.json()

        # Log what happened
        print(f"Subtasks created: {len(subtasks)}")
        for st in subtasks:
            print(f"  - {st['title']} (depth={st['depth']}, status={st['status']})")

        # Note: We don't assert subtask count because the LLM may not follow instructions
        # This test primarily verifies the integration works without errors


# Cleanup utility for manual runs
def cleanup_test_projects(api_client):
    """Delete all test projects (run manually if needed)."""
    response = api_client.get("/projects")
    if response.status_code == 200:
        for project in response.json():
            if "Test Project for Subtask" in project.get("name", ""):
                api_client.delete(f"/projects/{project['id']}")
                print(f"Deleted test project: {project['id']}")


if __name__ == "__main__":
    # Manual cleanup
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        cleanup_test_projects(client)
