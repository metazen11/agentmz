"""Workflow Tools for Open Interpreter.

This module exposes the workflow MCP tools as Python functions that can be
called by Open Interpreter agents. Instead of MCP protocol, we use direct
database access via the existing services.

Usage in prompts:
    The agent can call these functions directly in Python code blocks.
"""
import os
import sys
import json
from typing import Dict, Any, Optional, List

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy imports to avoid circular dependencies
_db = None
_services_loaded = False


def _get_db():
    """Get database session lazily."""
    global _db
    if _db is None:
        from app.db import SessionLocal
        _db = SessionLocal()
    return _db


def _ensure_services():
    """Ensure services are loaded."""
    global _services_loaded
    if not _services_loaded:
        from dotenv import load_dotenv
        load_dotenv()
        _services_loaded = True


# =============================================================================
# Context Tools
# =============================================================================

def get_task_context(task_id: int) -> Dict[str, Any]:
    """Get comprehensive task context for an agent.

    Returns task details, project config, work cycles, proofs, and recent history.
    This is the primary tool to understand what needs to be done.

    Args:
        task_id: The task ID (numeric, not task_id string like 'T020')

    Returns:
        Dict with task, project, work_cycles, proofs, and recent_history
    """
    _ensure_services()
    from app.models.task import Task
    from app.models.project import Project
    from app.models.work_cycle import WorkCycle
    from app.models.proof import Proof
    from app.models.report import AgentReport

    db = _get_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": f"Task {task_id} not found"}

    project = db.query(Project).filter(Project.id == task.project_id).first()

    # Get work cycles for this task (recent first)
    work_cycles = db.query(WorkCycle).filter(
        WorkCycle.task_id == task_id
    ).order_by(WorkCycle.created_at.desc()).limit(5).all()

    # Get proofs for this task
    proofs = db.query(Proof).filter(Proof.task_id == task_id).all()

    # Get recent agent reports for this task's project (last 5)
    recent_reports = []
    if project:
        from app.models.run import Run
        # Get runs for this project
        runs = db.query(Run).filter(Run.project_id == project.id).order_by(Run.created_at.desc()).limit(3).all()
        run_ids = [r.id for r in runs]
        if run_ids:
            reports = db.query(AgentReport).filter(
                AgentReport.run_id.in_(run_ids)
            ).order_by(AgentReport.created_at.desc()).limit(5).all()
            recent_reports = [
                {
                    "role": r.role.value if hasattr(r.role, 'value') else str(r.role),
                    "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                    "summary": r.summary[:200] if r.summary else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reports
            ]

    return {
        "task": {
            "id": task.id,
            "task_id": task.task_id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
            "pipeline_stage": task.pipeline_stage.value if hasattr(task.pipeline_stage, 'value') else str(task.pipeline_stage),
            "priority": task.priority,
            "acceptance_criteria": task.acceptance_criteria or [],
        },
        "project": {
            "id": project.id if project else None,
            "name": project.name if project else None,
            "repo_path": project.repo_path if project else None,
            "build_command": project.build_command if project else None,
            "test_command": project.test_command if project else None,
            "run_command": project.run_command if project else None,
        } if project else None,
        "recent_history": recent_reports,  # Recent agent work
        "work_cycles": [
            {
                "id": wc.id,
                "stage": wc.stage,
                "status": wc.status,
                "created_at": wc.created_at.isoformat() if wc.created_at else None,
            }
            for wc in work_cycles
        ],
        "proofs": [
            {
                "id": p.id,
                "proof_type": p.proof_type,
                "stage": p.stage,
                "description": p.description,
            }
            for p in proofs
        ],
    }


def format_task_prompt(task_id: int, role: str = "dev") -> str:
    """Format task context as a prompt string for any LLM provider.

    Order optimized for recency bias (most important info last):
    1. Recent History - what's been done
    2. Tools - what the agent can use
    3. Acceptance Criteria - how we know it's done
    4. Task Objective - what needs to be done (LAST = most attention)

    Args:
        task_id: The task ID
        role: Agent role (dev, qa, security, etc.)

    Returns:
        Formatted prompt string
    """
    context = get_task_context(task_id)

    if "error" in context:
        return f"Error: {context['error']}"

    task = context["task"]
    project = context.get("project", {})
    history = context.get("recent_history", [])

    sections = []

    # 1. RECENT HISTORY (oldest info - read first, forgotten first)
    sections.append("## Recent History")
    if history:
        for h in reversed(history):  # Show oldest first
            sections.append(f"- [{h['role'].upper()}] {h['status']}: {h['summary'] or 'No summary'}")
    else:
        sections.append("No previous agent work on this task.")
    sections.append("")

    # 2. TOOLS AVAILABLE
    sections.append("## Tools Available")
    sections.append(f"""You can execute code to complete your task.

**Project Commands:**
- Build: {project.get('build_command') or 'Not specified'}
- Test: {project.get('test_command') or 'pytest tests/ -v'}
- Run: {project.get('run_command') or 'Not specified'}

**Save Evidence:**
- Screenshots: Save to _proofs/*.png
- Logs: Save to _proofs/*.log
- Reports: Save to _proofs/*.json
""")

    # 3. ACCEPTANCE CRITERIA
    sections.append("## Acceptance Criteria")
    criteria = task.get("acceptance_criteria", [])
    if criteria:
        for i, c in enumerate(criteria, 1):
            sections.append(f"{i}. {c}")
    else:
        sections.append("No specific criteria defined.")
    sections.append("")

    # 4. TASK OBJECTIVE (LAST - gets most attention)
    sections.append("## Your Task")
    sections.append(f"**{task['task_id']}**: {task['title']}")
    sections.append("")
    sections.append(f"**Stage**: {task['pipeline_stage']} | **Role**: {role.upper()}")
    sections.append("")
    if task.get("description"):
        sections.append(f"**Description**: {task['description']}")
    sections.append("")
    sections.append(f"**Workspace**: {project.get('repo_path', 'Not specified')}")

    return "\n".join(sections)


def get_task(task_id: int) -> Dict[str, Any]:
    """Get task details by ID.

    Args:
        task_id: The task ID

    Returns:
        Task dict with all fields
    """
    _ensure_services()
    from app.models.task import Task

    db = _get_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": f"Task {task_id} not found"}

    return task.to_dict()


def get_project(project_id: int) -> Dict[str, Any]:
    """Get project configuration.

    Args:
        project_id: The project ID

    Returns:
        Project dict with commands, tech stack, key files
    """
    _ensure_services()
    from app.models.project import Project

    db = _get_db()
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": f"Project {project_id} not found"}

    return project.to_dict()


def list_tasks(project_id: int = None, status: str = None, limit: int = 20) -> List[Dict]:
    """List tasks with optional filters.

    Args:
        project_id: Filter by project
        status: Filter by status (backlog, in_progress, done)
        limit: Max results

    Returns:
        List of task dicts
    """
    _ensure_services()
    from app.models.task import Task

    db = _get_db()
    query = db.query(Task)

    if project_id:
        query = query.filter(Task.project_id == project_id)
    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.priority.desc()).limit(limit).all()
    return [t.to_dict() for t in tasks]


# =============================================================================
# Task Management Tools
# =============================================================================

def update_task_status(task_id: int, status: str) -> Dict[str, Any]:
    """Update task status.

    Args:
        task_id: The task ID
        status: New status (backlog, in_progress, done, blocked)

    Returns:
        Updated task dict
    """
    _ensure_services()
    from app.models.task import Task, TaskStatus

    db = _get_db()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return {"error": f"Task {task_id} not found"}

    # Map string to enum
    status_map = {
        "backlog": TaskStatus.BACKLOG,
        "in_progress": TaskStatus.IN_PROGRESS,
        "done": TaskStatus.DONE,
        "blocked": TaskStatus.BLOCKED,
    }

    if status.lower() not in status_map:
        return {"error": f"Invalid status: {status}"}

    task.status = status_map[status.lower()]
    db.commit()

    return {"success": True, "task": task.to_dict()}


def add_subtask(parent_task_id: int, title: str, description: str = "") -> Dict[str, Any]:
    """Create a subtask under a parent task.

    Args:
        parent_task_id: Parent task ID
        title: Subtask title
        description: Optional description

    Returns:
        New subtask dict
    """
    _ensure_services()
    from app.models.task import Task, TaskStatus

    db = _get_db()
    parent = db.query(Task).filter(Task.id == parent_task_id).first()
    if not parent:
        return {"error": f"Parent task {parent_task_id} not found"}

    # Generate subtask ID
    existing_subtasks = db.query(Task).filter(
        Task.parent_task_id == parent_task_id
    ).count()
    subtask_id = f"{parent.task_id}-{existing_subtasks + 1}"

    subtask = Task(
        project_id=parent.project_id,
        task_id=subtask_id,
        title=title,
        description=description,
        status=TaskStatus.BACKLOG,
        priority=parent.priority,
        parent_task_id=parent_task_id,
    )
    db.add(subtask)
    db.commit()
    db.refresh(subtask)

    return {"success": True, "subtask": subtask.to_dict()}


def complete_subtask(subtask_id: int) -> Dict[str, Any]:
    """Mark a subtask as done.

    Args:
        subtask_id: Subtask ID

    Returns:
        Updated subtask dict
    """
    return update_task_status(subtask_id, "done")


# =============================================================================
# Proof-of-Work Tools
# =============================================================================

def add_proof(task_id: int, filepath: str, proof_type: str, stage: str,
              description: str = "") -> Dict[str, Any]:
    """Add a proof artifact to document completed work.

    Args:
        task_id: The task ID
        filepath: Path to the proof file (screenshot, log, etc.)
        proof_type: Type of proof (screenshot, log, report)
        stage: Pipeline stage (dev, qa, sec, docs)
        description: Description of what this proves

    Returns:
        Proof record dict
    """
    _ensure_services()
    import requests

    if not os.path.exists(filepath):
        return {"error": f"File not found: {filepath}"}

    hub_url = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")

    with open(filepath, "rb") as f:
        files = {"file": (os.path.basename(filepath), f)}
        data = {
            "task_id": task_id,
            "proof_type": proof_type,
            "stage": stage,
            "description": description,
        }
        response = requests.post(
            f"{hub_url}/api/tasks/{task_id}/proofs/upload",
            files=files,
            data=data,
            timeout=30
        )

    if response.status_code in (200, 201):
        return {"success": True, "proof": response.json()}
    else:
        return {"error": f"Upload failed: {response.text}"}


def list_proofs(task_id: int) -> List[Dict]:
    """List proof artifacts for a task.

    Args:
        task_id: The task ID

    Returns:
        List of proof dicts
    """
    _ensure_services()
    from app.models.proof import Proof

    db = _get_db()
    proofs = db.query(Proof).filter(Proof.task_id == task_id).all()
    return [p.to_dict() for p in proofs]


# =============================================================================
# Report Tool
# =============================================================================

def submit_report(task_id: int, status: str, summary: str,
                  details: Dict = None) -> Dict[str, Any]:
    """Submit agent work report for a task.

    This is how agents report their work completion.

    Args:
        task_id: The task ID
        status: 'pass' or 'fail'
        summary: Brief description of work done
        details: Optional details dict

    Returns:
        Submission result
    """
    _ensure_services()
    import requests

    hub_url = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")

    response = requests.post(
        f"{hub_url}/api/tasks/{task_id}/work_cycle/complete",
        json={
            "report_status": status,
            "report_summary": summary,
            "report_details": details or {},
        },
        timeout=30
    )

    if response.status_code == 200:
        return {"success": True, "result": response.json()}
    else:
        return {"error": f"Submit failed: {response.text}"}


# =============================================================================
# Tool Documentation
# =============================================================================

TOOLS_HELP = """
# Workflow Tools

These Python functions are available for managing tasks and submitting work:

## Context Tools
- get_task_context(task_id) - Get comprehensive task context (START HERE)
- get_task(task_id) - Get task details
- get_project(project_id) - Get project config
- list_tasks(project_id, status, limit) - List tasks

## Task Management
- update_task_status(task_id, status) - Update task status
- add_subtask(parent_task_id, title, description) - Create subtask
- complete_subtask(subtask_id) - Mark subtask done

## Proof-of-Work
- add_proof(task_id, filepath, proof_type, stage, description) - Upload proof
- list_proofs(task_id) - List existing proofs

## Reporting
- submit_report(task_id, status, summary, details) - Submit work report

Example workflow:
1. context = get_task_context(689)
2. # Do the work...
3. add_proof(689, 'screenshot.png', 'screenshot', 'dev', 'Completed UI')
4. submit_report(689, 'pass', 'Fixed the bug', {'files_changed': ['app.py']})
"""


def get_help() -> str:
    """Get documentation about available tools."""
    return TOOLS_HELP
