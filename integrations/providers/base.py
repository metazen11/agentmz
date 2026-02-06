"""Abstract base class for external task providers.

All provider implementations must extend TaskIntegrationProvider and
implement the required abstract methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExternalAttachment:
    """Represents an attachment from an external system."""

    external_id: str
    filename: str
    url: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None


@dataclass
class ExternalTask:
    """Represents a task from an external system.

    This is the normalized task format used across all providers.
    Provider implementations convert their native task format to this.
    """

    external_id: str
    title: str
    description: Optional[str] = None
    completed: bool = False
    external_url: Optional[str] = None
    subtasks: list["ExternalTask"] = field(default_factory=list)
    attachments: list[ExternalAttachment] = field(default_factory=list)
    # Provider-specific metadata
    metadata: dict = field(default_factory=dict)


@dataclass
class ExternalProject:
    """Represents a project/workspace from an external system."""

    external_id: str
    name: str
    external_url: Optional[str] = None
    # Provider-specific metadata
    metadata: dict = field(default_factory=dict)


class TaskIntegrationProvider(ABC):
    """Abstract base class for external task providers.

    Implementations should:
    - Accept a decrypted API token in __init__
    - Implement all abstract methods
    - Return normalized ExternalTask/ExternalProject objects
    - Handle pagination internally
    - Raise appropriate exceptions on API errors
    """

    # Provider identifier (e.g., "asana", "jira")
    provider_name: str = "unknown"

    def __init__(self, token: str):
        """Initialize the provider with an API token.

        Args:
            token: Decrypted API token for authentication
        """
        self.token = token

    @abstractmethod
    def validate_credential(self) -> bool:
        """Validate that the API token is valid.

        Returns:
            True if the token is valid and can authenticate

        Raises:
            Exception: On network or API errors
        """
        pass

    @abstractmethod
    def list_projects(self) -> list[ExternalProject]:
        """List all accessible projects/workspaces.

        Returns:
            List of ExternalProject objects

        Raises:
            Exception: On network or API errors
        """
        pass

    @abstractmethod
    def list_tasks(self, project_id: str) -> list[ExternalTask]:
        """List all tasks in a project (excluding subtasks).

        Args:
            project_id: External project ID (e.g., Asana project gid)

        Returns:
            List of ExternalTask objects (top-level only)

        Raises:
            Exception: On network or API errors
        """
        pass

    @abstractmethod
    def get_task(self, task_id: str, include_subtasks: bool = True) -> ExternalTask:
        """Get detailed task information.

        Args:
            task_id: External task ID
            include_subtasks: Whether to fetch subtasks recursively

        Returns:
            ExternalTask with full details

        Raises:
            Exception: On network or API errors
        """
        pass

    # Optional methods for bidirectional sync (override in subclass)

    def update_task_status(self, task_id: str, completed: bool) -> bool:
        """Update task completion status in external system.

        Args:
            task_id: External task ID
            completed: New completion status

        Returns:
            True if update succeeded

        Raises:
            NotImplementedError: If provider doesn't support sync-back
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support status sync-back"
        )

    def add_comment(self, task_id: str, text: str) -> bool:
        """Add a comment to a task in the external system.

        Args:
            task_id: External task ID
            text: Comment text

        Returns:
            True if comment was added

        Raises:
            NotImplementedError: If provider doesn't support comments
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support adding comments"
        )

    @abstractmethod
    def export_task(
        self,
        title: str,
        description: str,
        completed: bool,
        external_project_id: str,
    ) -> ExternalTask:
        """Create a new task in the external system.
        Args:
            title: Task title
            description: Task description
            completed: Task completion status
            external_project_id: The ID of the project in the external system
        Returns:
            The created ExternalTask
        Raises:
            NotImplementedError: If provider doesn't support task export
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
