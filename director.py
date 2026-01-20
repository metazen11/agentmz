"""Director daemon - simple polling loop to orchestrate tasks."""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from database import SessionLocal
from models import Project, Task, TaskNode
from agent.runner import run_agent

# Configuration
POLL_INTERVAL = 10  # seconds


class Director:
    """Simple director that picks up tasks and runs agents."""

    def __init__(self):
        self.running = False

    def get_db(self):
        """Get a database session."""
        return SessionLocal()

    def run_once(self) -> dict:
        """Run one director cycle. Returns actions taken."""
        actions = []

        db = self.get_db()
        try:
            # Check for completed tasks first (result.json present)
            actions.extend(self._check_completed_tasks(db))

            # Then pick up new tasks to process
            actions.extend(self._process_pending_tasks(db))

            db.commit()
        except Exception as e:
            db.rollback()
            actions.append({"error": str(e)})
        finally:
            db.close()

        return {"actions": actions, "timestamp": datetime.now().isoformat()}

    def _check_completed_tasks(self, db) -> list:
        """Check for tasks with result.json and advance their node."""
        actions = []

        # Find in_progress tasks
        tasks = db.query(Task).filter(Task.status == "in_progress").all()

        for task in tasks:
            project = db.query(Project).filter(Project.id == task.project_id).first()
            if not project:
                continue

            result = self._read_result(project.workspace_path, task.id)
            if not result:
                continue

            # Verify result is for this task
            if result.get("task_id") != task.id:
                continue

            actions.append({
                "action": "check_result",
                "task_id": task.id,
                "result_status": result.get("status"),
            })

            # Route based on result
            if result.get("status") == "PASS":
                next_node = self._next_node(task.node, db)
                if next_node:
                    task.node_id = next_node.id
                else:
                    task.status = "done"
                actions.append({
                    "action": "advance_node",
                    "task_id": task.id,
                    "new_node": next_node.name if next_node else None,
                })
            else:
                # Failed - mark task for retry or investigation
                actions.append({
                    "action": "failed",
                    "task_id": task.id,
                    "summary": result.get("summary", "Unknown failure"),
                })

            # Clear the result file
            self._clear_result(project.workspace_path)

        return actions

    def _process_pending_tasks(self, db) -> list:
        """Pick up backlog tasks and start processing them."""
        actions = []

        # Find tasks that need work (backlog or in_progress but not complete)
        task = db.query(Task).filter(Task.status == "backlog").first()

        if not task:
            return actions

        project = db.query(Project).filter(Project.id == task.project_id).first()
        if not project:
            return actions

        # Mark as in_progress
        task.status = "in_progress"
        actions.append({
            "action": "start_task",
            "task_id": task.id,
            "task_title": task.title,
            "node": task.node_name,
        })

        # Write context.json
        self._write_context(project.workspace_path, task)

        # Run the agent (synchronously for now)
        try:
            result = run_agent(
                workspace_path=project.workspace_path,
                task_title=task.title,
                task_description=task.description or "",
                task_id=task.id,
                node_name=task.node_name or "dev",
            )
            actions.append({
                "action": "agent_complete",
                "task_id": task.id,
                "result": result.get("status"),
            })
        except Exception as e:
            actions.append({
                "action": "agent_error",
                "task_id": task.id,
                "error": str(e),
            })

        return actions

    def _next_node(self, current_node: TaskNode, db) -> Optional[TaskNode]:
        """Get the next node in the pipeline."""
        if not current_node:
            return None
        order = ["pm", "dev", "qa", "security", "documentation"]
        try:
            idx = order.index(current_node.name)
        except ValueError:
            return None
        if idx >= len(order) - 1:
            return None
        next_name = order[idx + 1]
        return db.query(TaskNode).filter(TaskNode.name == next_name).first()

    def _read_result(self, workspace_path: str, task_id: int) -> Optional[dict]:
        """Read result.json from workspace."""
        result_path = Path(workspace_path) / ".pipeline" / "result.json"
        if not result_path.exists():
            return None
        try:
            data = json.loads(result_path.read_text())
            return data
        except Exception:
            return None

    def _clear_result(self, workspace_path: str):
        """Remove result.json after processing."""
        result_path = Path(workspace_path) / ".pipeline" / "result.json"
        if result_path.exists():
            result_path.unlink()

    def _write_context(self, workspace_path: str, task: Task):
        """Write context.json for the agent."""
        pipeline_dir = Path(workspace_path) / ".pipeline"
        pipeline_dir.mkdir(parents=True, exist_ok=True)

        context = {
            "task_id": task.id,
            "title": task.title,
            "description": task.description,
            "node": task.node_name,
            "timestamp": datetime.now().isoformat(),
        }
        context_path = pipeline_dir / "context.json"
        context_path.write_text(json.dumps(context, indent=2))

    def run_loop(self):
        """Run the director loop continuously."""
        self.running = True
        print(f"Director starting... (poll interval: {POLL_INTERVAL}s)")

        while self.running:
            try:
                result = self.run_once()
                if result["actions"]:
                    print(f"[{result['timestamp']}] Actions: {result['actions']}")
            except Exception as e:
                print(f"Error in director loop: {e}")

            time.sleep(POLL_INTERVAL)

        print("Director stopped.")

    def stop(self):
        """Stop the director loop."""
        self.running = False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Director daemon")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    director = Director()

    if args.once:
        result = director.run_once()
        print(json.dumps(result, indent=2))
    else:
        try:
            director.run_loop()
        except KeyboardInterrupt:
            director.stop()
