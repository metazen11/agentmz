"""
End-to-end test: Create a project and animated hello world HTML file.

This test simulates a user:
1. Creating a new project with a workspace
2. Creating a task to build an animated hello world HTML file
3. Triggering the agent to do the work
4. Verifying the file was created correctly
"""
import os
import shutil
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import SessionLocal, engine
from models import Base, Project, Task, TaskComment, TaskAttachment, TaskAcceptanceCriteria, TaskNode, TaskRun


@pytest.fixture(scope="module")
def test_workspace():
    """Create a temporary workspace directory for testing."""
    workspace = tempfile.mkdtemp(prefix="agentic_test_")
    os.environ["WORKSPACES_DIR"] = str(Path(workspace).parent)
    yield workspace
    # Cleanup after tests
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database(db_cleanup_allowed):
    """Ensure database tables exist."""
    if not db_cleanup_allowed:
        pytest.skip("DB cleanup disabled; set ALLOW_DB_CLEANUP=1 or use a test database.")
    Base.metadata.create_all(bind=engine)
    yield
    # Optional: clean up test data after module
    db = SessionLocal()
    try:
        db.query(TaskRun).delete()
        db.query(TaskAttachment).delete()
        db.query(TaskComment).delete()
        db.query(TaskAcceptanceCriteria).delete()
        db.query(Task).delete()
        db.query(Project).delete()
        db.query(TaskNode).delete()
        db.commit()
    finally:
        db.close()


def _ensure_node(name: str) -> int:
    db = SessionLocal()
    try:
        node = db.query(TaskNode).filter(TaskNode.name == name).first()
        if not node:
            node = TaskNode(name=name, agent_prompt=f"{name} workflow.")
            db.add(node)
            db.commit()
            db.refresh(node)
        return node.id
    finally:
        db.close()


class TestProjectCreation:
    """Test creating a project like a user would."""

    def test_create_project(self, client, test_workspace):
        """User creates a new project with a workspace path."""
        response = client.post("/projects", json={
            "name": "Hello World Demo",
            "workspace_path": test_workspace,
            "environment": "local",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Hello World Demo"
        assert data["workspace_path"] == test_workspace
        assert data["environment"] == "local"
        assert "id" in data

        # Store for later tests
        TestProjectCreation.project_id = data["id"]

    def test_list_projects(self, client):
        """User can see their project in the list."""
        response = client.get("/projects")

        assert response.status_code == 200
        projects = response.json()
        assert len(projects) >= 1
        assert any(p["name"] == "Hello World Demo" for p in projects)

    def test_get_project_details(self, client):
        """User can view project details."""
        response = client.get(f"/projects/{TestProjectCreation.project_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Hello World Demo"


class TestTaskCreation:
    """Test creating tasks for the animated hello world."""

    def test_create_hello_world_task(self, client):
        """User creates a task to build an animated hello world page."""
        node_id = _ensure_node("dev")
        response = client.post("/tasks", json={
            "project_id": TestProjectCreation.project_id,
            "node_id": node_id,
            "title": "Create animated Hello World page",
            "description": """Create an index.html file with:
1. A centered "Hello World" heading
2. CSS animation that makes the text:
   - Fade in on page load
   - Gently pulse or glow continuously
   - Have a nice gradient or color effect
3. Clean, modern styling with a dark background
4. The animation should be smooth and professional-looking

Use pure CSS animations, no JavaScript required for the animation itself.""",
            "acceptance_criteria": [
                {"description": "Hello World page meets design requirements", "passed": False, "author": "user"},
            ],
        })

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Create animated Hello World page"
        assert data["status"] == "backlog"
        assert data["node_name"] == "dev"
        assert data["project_id"] == TestProjectCreation.project_id

        TestTaskCreation.task_id = data["id"]

    def test_list_project_tasks(self, client):
        """User can see tasks for the project."""
        response = client.get(f"/projects/{TestProjectCreation.project_id}/tasks")

        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) >= 1
        assert any(t["title"] == "Create animated Hello World page" for t in tasks)

    def test_create_subtask(self, client):
        """User can create a subtask."""
        node_id = _ensure_node("dev")
        response = client.post("/tasks", json={
            "project_id": TestProjectCreation.project_id,
            "parent_id": TestTaskCreation.task_id,
            "node_id": node_id,
            "title": "Add hover effect",
            "description": "Add a subtle hover effect to the heading",
            "acceptance_criteria": [
                {"description": "Hover effect is visible", "passed": False, "author": "user"},
            ],
        })

        assert response.status_code == 200
        data = response.json()
        assert data["parent_id"] == TestTaskCreation.task_id

    def test_task_tree_includes_subtasks(self, client):
        """Task tree should show subtasks nested under parent."""
        response = client.get(f"/projects/{TestProjectCreation.project_id}/tasks")

        assert response.status_code == 200
        tasks = response.json()

        # Find the parent task
        parent = next(t for t in tasks if t["title"] == "Create animated Hello World page")
        assert "children" in parent
        assert len(parent["children"]) == 1
        assert parent["children"][0]["title"] == "Add hover effect"


class TestTaskTrigger:
    """Test triggering the agent to work on tasks."""

    def test_trigger_task(self, client):
        """User triggers the agent to work on the task."""
        response = client.post(f"/tasks/{TestTaskCreation.task_id}/trigger")

        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == True
        assert data["task_id"] == TestTaskCreation.task_id

    def test_task_status_updated(self, client):
        """Task status should be updated to in_progress."""
        response = client.get(f"/tasks/{TestTaskCreation.task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"


class TestTaskUpdate:
    """Test updating tasks."""

    def test_update_task_status(self, client):
        """User can manually update task status."""
        node_id = _ensure_node("qa")
        response = client.patch(f"/tasks/{TestTaskCreation.task_id}", json={
            "status": "done",
            "node_id": node_id,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "done"
        assert data["node_name"] == "qa"


class TestDirectorEndpoints:
    """Test director endpoints."""

    def test_director_status(self, client):
        """User can check director status."""
        response = client.get("/director/status")

        assert response.status_code == 200
        data = response.json()
        assert "running" in data

    def test_director_cycle(self, client):
        """User can trigger a director cycle."""
        response = client.post("/director/cycle")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestAgentTools:
    """Test agent tools directly (unit tests)."""

    def test_list_files(self, test_workspace):
        """Test list_files tool."""
        from agent.tools import set_workspace, list_files

        set_workspace(test_workspace)

        # Create a test file
        Path(test_workspace, "test.txt").write_text("hello")

        result = list_files(".")
        assert "[F] test.txt" in result

    def test_read_file(self, test_workspace):
        """Test read_file tool."""
        from agent.tools import set_workspace, read_file

        set_workspace(test_workspace)
        Path(test_workspace, "test.txt").write_text("hello world")

        result = read_file("test.txt")
        assert result == "hello world"

    def test_edit_file_create_new(self, test_workspace):
        """Test edit_file to create a new file."""
        from agent.tools import set_workspace, edit_file

        set_workspace(test_workspace)

        # Create new file with empty search
        result = edit_file("new_file.txt", "", "This is new content")
        assert "Created" in result

        # Verify file exists
        content = Path(test_workspace, "new_file.txt").read_text()
        assert content == "This is new content"

    def test_edit_file_search_replace(self, test_workspace):
        """Test edit_file with search/replace (diff-based editing)."""
        from agent.tools import set_workspace, edit_file

        set_workspace(test_workspace)

        # Create initial file
        Path(test_workspace, "edit_test.txt").write_text("Hello World")

        # Edit using search/replace
        result = edit_file("edit_test.txt", "World", "Universe")
        assert "Edited" in result

        # Verify edit
        content = Path(test_workspace, "edit_test.txt").read_text()
        assert content == "Hello Universe"

    def test_edit_file_search_not_found(self, test_workspace):
        """Test edit_file when search text not found."""
        from agent.tools import set_workspace, edit_file

        set_workspace(test_workspace)
        Path(test_workspace, "search_test.txt").write_text("Hello World")

        result = edit_file("search_test.txt", "NotFound", "Replace")
        assert "not found" in result.lower()

    def test_run_command(self, test_workspace):
        """Test run_command tool."""
        from agent.tools import set_workspace, run_command

        set_workspace(test_workspace)

        result = run_command("echo 'test output'")
        assert "test output" in result


class TestAnimatedHelloWorldOutput:
    """Test that we can create the expected animated hello world file."""

    def test_create_animated_html_manually(self, test_workspace):
        """Demonstrate what the agent should create."""
        from agent.tools import set_workspace, edit_file

        set_workspace(test_workspace)

        # This is what we expect the agent to create
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        .hello-world {
            font-size: 4rem;
            font-weight: bold;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5, #00d2ff);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: fadeIn 1s ease-out, gradient 3s ease infinite, pulse 2s ease-in-out infinite;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes gradient {
            0% { background-position: 0% center; }
            50% { background-position: 100% center; }
            100% { background-position: 0% center; }
        }

        @keyframes pulse {
            0%, 100% {
                text-shadow: 0 0 20px rgba(0, 210, 255, 0.5);
            }
            50% {
                text-shadow: 0 0 40px rgba(0, 210, 255, 0.8), 0 0 60px rgba(58, 123, 213, 0.6);
            }
        }
    </style>
</head>
<body>
    <h1 class="hello-world">Hello World</h1>
</body>
</html>'''

        result = edit_file("index.html", "", html_content)
        assert "Created" in result

        # Verify file was created
        created_file = Path(test_workspace, "index.html")
        assert created_file.exists()

        content = created_file.read_text()
        assert "Hello World" in content
        assert "@keyframes" in content
        assert "animation" in content
        assert "fadeIn" in content
        assert "pulse" in content


class TestCleanup:
    """Test cleanup operations."""

    def test_delete_project(self, client):
        """User can delete a project."""
        # First create a project to delete
        response = client.post("/projects", json={
            "name": "To Delete",
            "workspace_path": "/tmp/delete-me",
            "environment": "local",
        })
        project_id = response.json()["id"]

        # Delete it
        response = client.delete(f"/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["deleted"] == True

        # Verify it's gone
        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
