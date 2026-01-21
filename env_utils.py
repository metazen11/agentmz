"""Shared environment loading utilities."""
from pathlib import Path
import os

from dotenv import load_dotenv


def load_env() -> Path:
    """Load .env from the project root if present."""
    root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent)).resolve()
    env_path = root / ".env"
    load_dotenv(env_path)
    return env_path


def get_workspaces_root() -> Path:
    """Resolve WORKSPACES_DIR, supporting relative paths via PROJECT_ROOT."""
    root_value = os.getenv("WORKSPACES_DIR", "/workspaces")
    root_path = Path(root_value)
    if not root_path.is_absolute():
        base_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent)).resolve()
        root_path = (base_root / root_path).resolve()
    return root_path


def resolve_workspace_path(workspace_path: str) -> Path:
    """Resolve workspace path, supporting [%root%] variable.

    Args:
        workspace_path: Workspace path from project, can be:
            - "[%root%]" -> resolves to PROJECT_ROOT
            - "[%root%]/subdir" -> resolves to PROJECT_ROOT/subdir
            - Regular workspace name -> joined with WORKSPACES_DIR

    Returns:
        Absolute Path to the workspace directory
    """
    if workspace_path.startswith("[%root%]"):
        # Get PROJECT_ROOT from env, fallback to /v2
        root = os.environ.get("PROJECT_ROOT", "/v2")
        resolved = workspace_path.replace("[%root%]", root)
        return Path(resolved)

    # Default: extract workspace name and join with WORKSPACES_DIR
    workspace_name = Path(workspace_path).name
    return get_workspaces_root() / workspace_name
