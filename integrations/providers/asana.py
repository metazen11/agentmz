"""Asana task provider implementation.

Uses Asana's REST API with Personal Access Token authentication.
https://developers.asana.com/docs/api-reference
"""

import logging
from typing import Optional
import httpx

from integrations.providers import register_provider
from integrations.providers.base import (
    TaskIntegrationProvider,
    ExternalProject,
    ExternalTask,
    ExternalAttachment,
)

logger = logging.getLogger(__name__)

ASANA_API_BASE = "https://app.asana.com/api/1.0"


@register_provider("asana")
class AsanaProvider(TaskIntegrationProvider):
    """Asana task integration provider.

    Uses Personal Access Token (PAT) for authentication.
    Generate a PAT at: https://app.asana.com/0/developer-console
    """

    provider_name = "asana"

    def __init__(self, token: str):
        """Initialize with Asana PAT.

        Args:
            token: Asana Personal Access Token
        """
        super().__init__(token)
        self._client = httpx.Client(
            base_url=ASANA_API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request to Asana API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/users/me")
            **kwargs: Additional arguments for httpx.request

        Returns:
            Response JSON data

        Raises:
            httpx.HTTPStatusError: On API errors
        """
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def _get_all_pages(self, path: str, params: Optional[dict] = None) -> list:
        """Fetch all pages of a paginated endpoint.

        Args:
            path: API path
            params: Query parameters

        Returns:
            Combined list of all items across pages
        """
        params = params or {}
        params.setdefault("limit", 100)
        all_items = []

        while True:
            response = self._request("GET", path, params=params)
            data = response.get("data", [])
            all_items.extend(data)

            # Check for next page
            next_page = response.get("next_page")
            if not next_page or not next_page.get("offset"):
                break

            params["offset"] = next_page["offset"]

        return all_items

    def validate_credential(self) -> bool:
        """Validate the PAT by fetching user info.

        Returns:
            True if token is valid
        """
        try:
            response = self._request("GET", "/users/me")
            user = response.get("data", {})
            logger.info(f"Asana token valid for user: {user.get('name', 'unknown')}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning("Asana token is invalid or expired")
                return False
            raise
        except Exception as e:
            logger.error(f"Failed to validate Asana token: {e}")
            raise

    def list_projects(self) -> list[ExternalProject]:
        """List all accessible projects across all workspaces.

        Returns:
            List of ExternalProject objects
        """
        # First get all workspaces
        workspaces = self._get_all_pages("/workspaces")

        projects = []
        for workspace in workspaces:
            workspace_gid = workspace.get("gid")
            workspace_name = workspace.get("name", "Unknown")

            # Get projects in this workspace
            ws_projects = self._get_all_pages(
                f"/workspaces/{workspace_gid}/projects",
                params={"opt_fields": "name,permalink_url"},
            )

            for proj in ws_projects:
                projects.append(
                    ExternalProject(
                        external_id=proj.get("gid"),
                        name=proj.get("name"),
                        external_url=proj.get("permalink_url"),
                        metadata={
                            "workspace_gid": workspace_gid,
                            "workspace_name": workspace_name,
                        },
                    )
                )

        logger.info(f"Found {len(projects)} Asana projects")
        return projects

    def list_tasks(self, project_id: str) -> list[ExternalTask]:
        """List all top-level tasks in a project.

        Args:
            project_id: Asana project gid

        Returns:
            List of ExternalTask objects (without subtasks populated)
        """
        tasks = self._get_all_pages(
            f"/projects/{project_id}/tasks",
            params={
                "opt_fields": "name,notes,completed,permalink_url",
            },
        )

        result = []
        for task in tasks:
            result.append(
                ExternalTask(
                    external_id=task.get("gid"),
                    title=task.get("name", ""),
                    description=task.get("notes"),
                    completed=task.get("completed", False),
                    external_url=task.get("permalink_url"),
                )
            )

        logger.info(f"Found {len(result)} tasks in project {project_id}")
        return result

    def get_task(self, task_id: str, include_subtasks: bool = True) -> ExternalTask:
        """Get detailed task information.

        Args:
            task_id: Asana task gid
            include_subtasks: Whether to fetch subtasks recursively

        Returns:
            ExternalTask with full details
        """
        # Fetch task details
        response = self._request(
            "GET",
            f"/tasks/{task_id}",
            params={
                "opt_fields": "name,notes,completed,permalink_url,custom_fields",
            },
        )
        task_data = response.get("data", {})

        task = ExternalTask(
            external_id=task_data.get("gid"),
            title=task_data.get("name", ""),
            description=task_data.get("notes"),
            completed=task_data.get("completed", False),
            external_url=task_data.get("permalink_url"),
            metadata={
                "custom_fields": task_data.get("custom_fields", []),
            },
        )

        # Fetch attachments
        task.attachments = self._get_attachments(task_id)

        # Fetch subtasks recursively
        if include_subtasks:
            task.subtasks = self._get_subtasks(task_id)

        return task

    def _get_subtasks(self, task_id: str) -> list[ExternalTask]:
        """Fetch subtasks for a task recursively.

        Args:
            task_id: Parent task gid

        Returns:
            List of ExternalTask objects
        """
        subtasks_data = self._get_all_pages(
            f"/tasks/{task_id}/subtasks",
            params={
                "opt_fields": "name,notes,completed,permalink_url",
            },
        )

        subtasks = []
        for st in subtasks_data:
            subtask = ExternalTask(
                external_id=st.get("gid"),
                title=st.get("name", ""),
                description=st.get("notes"),
                completed=st.get("completed", False),
                external_url=st.get("permalink_url"),
            )
            # Recursively get nested subtasks
            subtask.subtasks = self._get_subtasks(st.get("gid"))
            subtask.attachments = self._get_attachments(st.get("gid"))
            subtasks.append(subtask)

        return subtasks

    def _get_attachments(self, task_id: str) -> list[ExternalAttachment]:
        """Fetch attachments for a task.

        Args:
            task_id: Task gid

        Returns:
            List of ExternalAttachment objects
        """
        try:
            attachments_data = self._get_all_pages(
                f"/tasks/{task_id}/attachments",
                params={
                    "opt_fields": "name,download_url,size,resource_type",
                },
            )

            attachments = []
            for att in attachments_data:
                attachments.append(
                    ExternalAttachment(
                        external_id=att.get("gid"),
                        filename=att.get("name", ""),
                        url=att.get("download_url", ""),
                        size_bytes=att.get("size"),
                    )
                )
            return attachments
        except httpx.HTTPStatusError:
            # Attachments may not be accessible
            logger.debug(f"Could not fetch attachments for task {task_id}")
            return []

    def update_task_status(self, task_id: str, completed: bool) -> bool:
        """Update task completion status in Asana.

        Args:
            task_id: Asana task gid
            completed: New completion status

        Returns:
            True if update succeeded
        """
        try:
            self._request(
                "PUT",
                f"/tasks/{task_id}",
                json={"data": {"completed": completed}},
            )
            logger.info(f"Updated Asana task {task_id} completed={completed}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to update Asana task {task_id}: {e}")
            raise

    def add_comment(self, task_id: str, text: str) -> bool:
        """Add a comment (story) to an Asana task.

        Args:
            task_id: Asana task gid
            text: Comment text

        Returns:
            True if comment was added
        """
        try:
            self._request(
                "POST",
                f"/tasks/{task_id}/stories",
                json={"data": {"text": text}},
            )
            logger.info(f"Added comment to Asana task {task_id}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to add comment to Asana task {task_id}: {e}")
            raise

    def export_task(
        self,
        title: str,
        description: str,
        completed: bool,
        external_project_id: str,
    ) -> ExternalTask:
        """Create a new task in Asana.
        Args:
            title: Task title
            description: Task description
            completed: Task completion status
            external_project_id: The ID of the project in Asana
        Returns:
            The created ExternalTask
        """
        try:
            response = self._request(
                "POST",
                "/tasks",
                json={
                    "data": {
                        "name": title,
                        "notes": description,
                        "completed": completed,
                        "projects": [external_project_id],
                    }
                },
            )
            task_data = response.get("data", {})
            logger.info(f"Exported task to Asana with GID: {task_data.get('gid')}")
            return ExternalTask(
                external_id=task_data.get("gid"),
                title=task_data.get("name", ""),
                description=task_data.get("notes"),
                completed=task_data.get("completed", False),
                external_url=task_data.get("permalink_url"),
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to export task to Asana: {e}")
            raise

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "_client"):
            self._client.close()
