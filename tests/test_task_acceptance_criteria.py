"""Test task acceptance criteria APIs."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import SessionLocal, engine
from models import Base, Project, Task, TaskAcceptanceCriteria, TaskNode, TaskRun


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database(db_cleanup_allowed):
    if not db_cleanup_allowed:
        pytest.skip("DB cleanup disabled; set ALLOW_DB_CLEANUP=1 or use a test database.")
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    try:
        db.query(TaskRun).delete()
        db.query(TaskAcceptanceCriteria).delete()
        db.query(Task).delete()
        db.query(Project).delete()
        db.query(TaskNode).delete()
        db.commit()
    finally:
        db.close()


def _create_project(client, workspace_path):
    res = client.post("/projects", json={
        "name": "Acceptance Demo",
        "workspace_path": workspace_path,
        "environment": "local",
    })
    assert res.status_code == 200
    return res.json()


def _create_task(client, project_id):
    db = SessionLocal()
    try:
        node = db.query(TaskNode).filter(TaskNode.name == "dev").first()
        if not node:
            node = TaskNode(name="dev", agent_prompt="Development workflow.")
            db.add(node)
            db.commit()
            db.refresh(node)
        node_id = node.id
    finally:
        db.close()
    res = client.post("/tasks", json={
        "project_id": project_id,
        "node_id": node_id,
        "title": "Add acceptance criteria",
        "description": "Seed task for acceptance criteria tests.",
        "acceptance_criteria": [
            {"description": "Criteria can be created", "passed": False, "author": "user"},
        ],
    })
    assert res.status_code == 200
    return res.json()


def test_acceptance_criteria_flow(client, tmp_path):
    os.environ["WORKSPACES_DIR"] = str(tmp_path.parent)
    project = _create_project(client, str(tmp_path))
    task = _create_task(client, project["id"])

    # Create criteria
    res = client.post(f"/tasks/{task['id']}/acceptance", json={
        "description": "The endpoint returns 200",
        "passed": False,
        "author": "user",
    })
    assert res.status_code == 200
    criteria = res.json()
    assert criteria["task_id"] == task["id"]
    assert criteria["passed"] is False
    assert criteria["author"] == "user"

    # Update criteria
    res = client.patch(f"/tasks/{task['id']}/acceptance/{criteria['id']}", json={
        "passed": True,
    })
    assert res.status_code == 200
    updated = res.json()
    assert updated["passed"] is True

    # List criteria
    res = client.get(f"/tasks/{task['id']}/acceptance")
    assert res.status_code == 200
    criteria_list = res.json()
    assert any(item["id"] == criteria["id"] for item in criteria_list)

    # Delete criteria
    res = client.delete(f"/tasks/{task['id']}/acceptance/{criteria['id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
