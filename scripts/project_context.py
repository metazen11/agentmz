"""Project Context Manager - Aggregates context from multiple sources.

This module provides a unified interface for building project context
that gets injected into agent prompts. It follows a priority hierarchy:

Priority (highest to lowest):
1. Database (Project/Task records) - structured, persistent
2. Explicit files (project.md, task.md) - human-written instructions
3. Auto-discovery (ProjectDiscovery) - inferred from codebase

Usage:
    from project_context import ProjectContext

    ctx = ProjectContext(workspace_path="/workspaces/myproject")
    ctx.load_from_database(project_id=1, task_id=5)
    ctx.load_from_files()
    ctx.load_from_discovery()

    system_prompt = ctx.build_system_prompt()
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class TaskInfo:
    """Represents a task with its context."""
    id: int
    title: str
    description: Optional[str] = None
    status: str = "pending"
    node: str = "dev"


@dataclass
class ProjectContext:
    """Aggregated project context from multiple sources.

    Attributes:
        workspace_path: Absolute path to the workspace directory
        name: Project name
        description: Project description
        languages: Detected programming languages
        frameworks: Detected frameworks
        databases: Detected databases
        git_branch: Current git branch
        git_url: Repository URL
        test_command: How to run tests
        build_command: How to build
        run_command: How to run
        docker_services: Docker services in docker-compose
        api_routes: Discovered API routes
        env_variables: Required environment variables
        project_instructions: Content from project.md
        task_instructions: Content from task.md
        current_task: Current task being worked on
        task_history: Recent completed/failed tasks
    """
    workspace_path: str
    name: str = ""
    description: str = ""

    # Tech stack (from discovery)
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)

    # Git info
    git_branch: Optional[str] = None
    git_url: Optional[str] = None

    # Commands
    test_command: Optional[str] = None
    build_command: Optional[str] = None
    run_command: Optional[str] = None

    # Infrastructure
    docker_services: List[str] = field(default_factory=list)
    api_routes: List[str] = field(default_factory=list)
    env_variables: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)

    # Explicit instructions (from files)
    project_instructions: str = ""
    task_instructions: str = ""

    # Task context (from database)
    current_task: Optional[TaskInfo] = None
    task_history: List[TaskInfo] = field(default_factory=list)

    # Metadata
    _loaded_from: List[str] = field(default_factory=list)

    def load_from_database(self, project_id: int = None, task_id: int = None) -> "ProjectContext":
        """Load context from database records.

        Args:
            project_id: Project ID to load
            task_id: Current task ID (excluded from history)

        Returns:
            self for chaining
        """
        if not project_id:
            return self

        try:
            # Lazy import to avoid startup issues
            script_dir = Path(__file__).parent
            sys.path.insert(0, str(script_dir.parent))
            from database import SessionLocal
            from models import Project, Task

            db = SessionLocal()
            try:
                # Load project
                project = db.query(Project).filter(Project.id == project_id).first()
                if project:
                    self.name = project.name or self.name
                    # Could extend Project model to store more metadata
                    self._loaded_from.append("database:project")

                # Load task history
                tasks = db.query(Task).filter(
                    Task.project_id == project_id
                ).order_by(Task.created_at.desc()).limit(20).all()

                for task in tasks:
                    if task_id and task.id == task_id:
                        # Current task
                        self.current_task = TaskInfo(
                            id=task.id,
                            title=task.title,
                            description=task.description,
                            status=task.status,
                            node=task.node_name or "dev",
                        )
                    else:
                        # History
                        self.task_history.append(TaskInfo(
                            id=task.id,
                            title=task.title,
                            description=task.description,
                            status=task.status,
                            node=task.node_name or "dev",
                        ))

                if tasks:
                    self._loaded_from.append("database:tasks")

            finally:
                db.close()

        except Exception as e:
            print(f"[ProjectContext] Warning: Database load failed: {e}")

        return self

    def load_from_files(self) -> "ProjectContext":
        """Load context from project.md and task.md files.

        Returns:
            self for chaining
        """
        # Load project.md
        project_md = os.path.join(self.workspace_path, "project.md")
        if os.path.isfile(project_md):
            try:
                with open(project_md, "r", encoding="utf-8") as f:
                    self.project_instructions = f.read()
                    if len(self.project_instructions) > 5000:
                        self.project_instructions = self.project_instructions[:5000] + "\n\n[truncated]"
                self._loaded_from.append("file:project.md")
            except Exception as e:
                print(f"[ProjectContext] Warning: Could not read project.md: {e}")

        # Load task.md (check multiple locations)
        task_md_locations = [
            os.path.join(self.workspace_path, "task.md"),
            os.path.join(self.workspace_path, ".pipeline", "task.md"),
        ]
        for task_md in task_md_locations:
            if os.path.isfile(task_md):
                try:
                    with open(task_md, "r", encoding="utf-8") as f:
                        self.task_instructions = f.read()
                        if len(self.task_instructions) > 3000:
                            self.task_instructions = self.task_instructions[:3000] + "\n\n[truncated]"
                    self._loaded_from.append(f"file:{os.path.basename(task_md)}")
                    break
                except Exception as e:
                    print(f"[ProjectContext] Warning: Could not read task.md: {e}")

        return self

    def load_from_discovery(self) -> "ProjectContext":
        """Load context from ProjectDiscovery (auto-detect from codebase).

        Returns:
            self for chaining
        """
        try:
            from discover_project import ProjectDiscovery
            discovery = ProjectDiscovery(self.workspace_path)
            info = discovery.discover()

            # Only set if not already set (priority: DB > files > discovery)
            if not self.name:
                self.name = info.get("name", "")
            if not self.description:
                self.description = info.get("description", "")

            # Tech stack (always take from discovery)
            self.languages = info.get("languages", [])
            self.frameworks = info.get("frameworks", [])
            self.databases = info.get("databases", [])

            # Git
            self.git_branch = info.get("primary_branch")
            self.git_url = info.get("repository_url")

            # Commands
            self.test_command = info.get("test_command")
            self.build_command = info.get("build_command")
            self.run_command = info.get("run_command")

            # Infrastructure
            if info.get("docker_services"):
                self.docker_services = [s.get("name", "") for s in info["docker_services"][:5]]
            if info.get("api_routes"):
                self.api_routes = [r.get("path", "") for r in info["api_routes"][:10]]
            self.env_variables = info.get("env_variables", [])[:10]
            self.key_files = info.get("key_files", [])

            self._loaded_from.append("discovery")

        except ImportError:
            print("[ProjectContext] Warning: discover_project.py not available")
        except Exception as e:
            print(f"[ProjectContext] Warning: Discovery failed: {e}")

        return self

    def load_all(self, project_id: int = None, task_id: int = None) -> "ProjectContext":
        """Load context from all sources in priority order.

        Args:
            project_id: Optional project ID for database context
            task_id: Optional task ID for current task context

        Returns:
            self for chaining
        """
        self.load_from_database(project_id, task_id)
        self.load_from_files()
        self.load_from_discovery()
        return self

    def build_system_prompt(self) -> str:
        """Build the complete system prompt with all injected context.

        Returns:
            Complete system prompt string for the agent
        """
        parts = [self._base_agent_prompt()]

        # Project context section
        context_section = self._build_context_section()
        if context_section:
            parts.append(context_section)

        # Project instructions (from project.md)
        if self.project_instructions:
            parts.append(f"\n\n## Project Instructions\n\n{self.project_instructions}")

        # Task instructions (from task.md)
        if self.task_instructions:
            parts.append(f"\n\n## Current Task Instructions\n\n{self.task_instructions}")

        # Current task from database
        if self.current_task:
            parts.append(f"\n\n## Current Task\n\n**{self.current_task.title}**")
            if self.current_task.description:
                parts.append(f"\n{self.current_task.description}")
            parts.append(f"\nStatus: {self.current_task.status} | Node: {self.current_task.node}")

        # Task history
        if self.task_history:
            parts.append(self._build_history_section())

        print(f"[ProjectContext] Built prompt from: {', '.join(self._loaded_from)}")
        return "".join(parts)

    def _base_agent_prompt(self) -> str:
        """Return the base agent system prompt."""
        return """You are a coding agent. You have access to tools to explore and modify code.

Available tools:
- grep: Search for patterns in files
- glob: Find files by pattern
- read: Read file contents
- bash: Run shell commands
- write: Create NEW files only (files that don't exist yet)
- edit: Modify EXISTING files using AI diff editing (PREFERRED for changes)
- done: Signal task completion

TOOL SELECTION (IMPORTANT):
- For EXISTING files: Always use 'edit' - it preserves unchanged code
- For NEW files: Use 'write' to create them
- Before editing: Always 'read' the file first to understand its structure

Workflow:
1. First, explore the workspace to understand the codebase (use glob, read)
2. Search for relevant code (use grep)
3. Make necessary changes (use edit for existing files, write for new files)
4. Verify changes work (use bash to run tests)
5. Call done(status="PASS", summary="...") when complete

Always explore before editing. Be thorough but efficient."""

    def _build_context_section(self) -> str:
        """Build the project context section."""
        lines = ["\n\n## Project Context\n"]

        if self.name:
            lines.append(f"**Project:** {self.name}")
        if self.description:
            desc = self.description[:200] + "..." if len(self.description) > 200 else self.description
            lines.append(f"**Description:** {desc}")

        # Tech stack
        if self.languages:
            lines.append(f"**Languages:** {', '.join(self.languages)}")
        if self.frameworks:
            lines.append(f"**Frameworks:** {', '.join(self.frameworks)}")
        if self.databases:
            lines.append(f"**Databases:** {', '.join(self.databases)}")

        # Git
        if self.git_branch:
            lines.append(f"**Git Branch:** {self.git_branch}")

        # Commands
        if self.test_command:
            lines.append(f"**Run Tests:** `{self.test_command}`")
        if self.build_command:
            lines.append(f"**Build:** `{self.build_command}`")

        # Infrastructure
        if self.docker_services:
            lines.append(f"**Docker Services:** {', '.join(self.docker_services)}")
        if self.key_files:
            lines.append(f"**Key Files:** {', '.join(self.key_files)}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_history_section(self) -> str:
        """Build the task history section."""
        lines = ["\n\n## Recent Task History\n"]
        emoji_map = {"done": "✅", "failed": "❌", "in_progress": "🔄"}

        for task in self.task_history[:10]:
            emoji = emoji_map.get(task.status, "⏸️")
            lines.append(f"{emoji} **{task.title}** [{task.status}]")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Export context as dictionary for API responses."""
        return {
            "name": self.name,
            "description": self.description,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "databases": self.databases,
            "git_branch": self.git_branch,
            "git_url": self.git_url,
            "test_command": self.test_command,
            "build_command": self.build_command,
            "run_command": self.run_command,
            "docker_services": self.docker_services,
            "key_files": self.key_files,
            "has_project_instructions": bool(self.project_instructions),
            "has_task_instructions": bool(self.task_instructions),
            "current_task": self.current_task.title if self.current_task else None,
            "task_history_count": len(self.task_history),
            "loaded_from": self._loaded_from,
        }
