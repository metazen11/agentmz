"""Test task comments and attachments APIs."""
import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import SessionLocal, engine
from models import Base, Project, Task, TaskComment, TaskAttachment, TaskAcceptanceCriteria


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def uploads_dir():
    path = tempfile.mkdtemp(prefix="agentic_uploads_")
    os.environ["UPLOADS_DIR"] = path
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="module", autouse=True)
def setup_database(db_cleanup_allowed):
    if not db_cleanup_allowed:
        pytest.skip("DB cleanup disabled; set ALLOW_DB_CLEANUP=1 or use a test database.")
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    try:
        db.query(TaskAttachment).delete()
        db.query(TaskComment).delete()
        db.query(TaskAcceptanceCriteria).delete()
        db.query(Task).delete()
        db.query(Project).delete()
        db.commit()
    finally:
        db.close()


def _create_project(client, workspace_path):
    res = client.post("/projects", json={
        "name": "Comments Demo",
        "workspace_path": workspace_path,
        "environment": "local",
    })
    assert res.status_code == 200
    return res.json()


def _create_task(client, project_id):
    res = client.post("/tasks", json={
        "project_id": project_id,
        "title": "Add comments and attachments",
        "description": "Seed task for comments and attachments tests.",
    })
    assert res.status_code == 200
    return res.json()


def test_comment_and_attachment_flow(client, uploads_dir, tmp_path):
    os.environ["WORKSPACES_DIR"] = str(tmp_path.parent)
    project = _create_project(client, str(tmp_path))
    task = _create_task(client, project["id"])

    # Create comment
    res = client.post(f"/tasks/{task['id']}/comments", json={
        "author": "tester",
        "body": "First comment",
    })
    assert res.status_code == 200
    comment = res.json()
    assert comment["task_id"] == task["id"]
    assert comment["author"] == "tester"
    assert comment["body"] == "First comment"

    # Update comment
    res = client.patch(f"/tasks/{task['id']}/comments/{comment['id']}", json={
        "body": "Edited comment",
    })
    assert res.status_code == 200
    updated = res.json()
    assert updated["body"] == "Edited comment"

    # List comments
    res = client.get(f"/tasks/{task['id']}/comments")
    assert res.status_code == 200
    comments = res.json()
    assert any(c["id"] == comment["id"] for c in comments)

    # Upload attachment linked to comment
    res = client.post(
        f"/tasks/{task['id']}/attachments",
        data={"comment_id": str(comment["id"]), "uploaded_by": "tester"},
        files={"file": ("notes.txt", b"hello attachment", "text/plain")},
    )
    assert res.status_code == 200
    attachment = res.json()
    assert attachment["task_id"] == task["id"]
    assert attachment["comment_id"] == comment["id"]
    assert attachment["filename"] == "notes.txt"
    assert attachment["storage_path"]
    assert attachment["url"]

    # List attachments (task)
    res = client.get(f"/tasks/{task['id']}/attachments")
    assert res.status_code == 200
    attachments = res.json()
    assert any(a["id"] == attachment["id"] for a in attachments)

    # List attachments (comment)
    res = client.get(f"/tasks/{task['id']}/attachments", params={"comment_id": comment["id"]})
    assert res.status_code == 200
    attachments = res.json()
    assert len(attachments) == 1
    assert attachments[0]["id"] == attachment["id"]

    # Download attachment
    res = client.get(f"/tasks/{task['id']}/attachments/{attachment['id']}/download")
    assert res.status_code == 200
    assert res.content == b"hello attachment"

    # Delete attachment
    res = client.delete(f"/tasks/{task['id']}/attachments/{attachment['id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True

    # Delete comment
    res = client.delete(f"/tasks/{task['id']}/comments/{comment['id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
