"""Test task nodes and run tracking APIs."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import SessionLocal, engine
from models import Base, Project, Task, TaskRun, TaskNode, TaskAcceptanceCriteria


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


def test_node_and_run_flow(client, tmp_path):
    os.environ["WORKSPACES_DIR"] = str(tmp_path.parent)

    # Create node
    res = client.post("/nodes", json={
        "name": "dev",
        "agent_prompt": "You are a developer. Implement requested changes.",
    })
    assert res.status_code == 200
    node = res.json()
    node_id = node["id"]

    # Create project
    res = client.post("/projects", json={
        "name": "Run Demo",
        "workspace_path": str(tmp_path),
        "environment": "local",
    })
    assert res.status_code == 200
    project = res.json()

    # Create task with acceptance criteria
    res = client.post("/tasks", json={
        "project_id": project["id"],
        "node_id": node_id,
        "title": "Run tracking test",
        "description": "Seed task for run tracking.",
        "acceptance_criteria": [
            {"description": "Run tracking works", "passed": False, "author": "user"},
        ],
    })
    assert res.status_code == 200
    task = res.json()

    # Create run
    res = client.post(f"/tasks/{task['id']}/runs", json={"node_id": node_id})
    assert res.status_code == 200
    run = res.json()
    assert run["status"] == "started"

    # Update run
    res = client.patch(
        f"/tasks/{task['id']}/runs/{run['id']}",
        json={"status": "completed", "summary": "Completed run"},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["status"] == "completed"
    assert updated["summary"] == "Completed run"

    # List runs
    res = client.get(f"/tasks/{task['id']}/runs")
    assert res.status_code == 200
    runs = res.json()
    assert any(r["id"] == run["id"] for r in runs)
