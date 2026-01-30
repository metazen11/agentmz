"""File autocomplete widget for @ mentions."""
import os
from pathlib import Path
from typing import Callable

from textual.suggester import Suggester, SuggestFromList
from textual.widgets import Input


class FileAutocompleteSuggester(Suggester):
    """Suggester that provides file completions when @ is typed."""

    def __init__(self, workspace: str, case_sensitive: bool = False):
        super().__init__(use_cache=False, case_sensitive=case_sensitive)
        self.workspace = workspace
        self._file_cache: list[str] | None = None

    def _scan_files(self, max_files: int = 500) -> list[str]:
        """Scan workspace for files, caching results."""
        if self._file_cache is not None:
            return self._file_cache

        files = []
        workspace_path = Path(self.workspace)

        if not workspace_path.exists():
            return []

        # Walk workspace, skip hidden and common ignore patterns
        ignore_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".cache"}

        for root, dirs, filenames in os.walk(workspace_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]

            for filename in filenames:
                if filename.startswith("."):
                    continue
                filepath = Path(root) / filename
                relpath = filepath.relative_to(workspace_path)
                files.append(str(relpath))

                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break

        self._file_cache = sorted(files)
        return self._file_cache

    def invalidate_cache(self) -> None:
        """Clear the file cache to force rescan."""
        self._file_cache = None

    async def get_suggestion(self, value: str) -> str | None:
        """Get file suggestion when @ is typed."""
        # Find the last @ in the input
        at_pos = value.rfind("@")
        if at_pos == -1:
            return None

        # Get the partial path after @
        partial = value[at_pos + 1:]

        # Don't suggest if there's a space after @ (completed)
        if " " in partial:
            return None

        # Get matching files
        files = self._scan_files()
        partial_lower = partial.lower() if not self.case_sensitive else partial

        for filepath in files:
            check_path = filepath.lower() if not self.case_sensitive else filepath

            # Match if partial is prefix or fuzzy match
            if check_path.startswith(partial_lower) or partial_lower in check_path:
                # Return the full value with completion
                return value[:at_pos + 1] + filepath

        return None


class FileInput(Input):
    """Input widget with @ file autocomplete support."""

    def __init__(
        self,
        workspace: str = ".",
        *args,
        **kwargs,
    ):
        self.workspace = workspace
        self._file_suggester = FileAutocompleteSuggester(workspace)
        super().__init__(*args, suggester=self._file_suggester, **kwargs)

    def set_workspace(self, workspace: str) -> None:
        """Update the workspace for file suggestions."""
        self.workspace = workspace
        self._file_suggester.workspace = workspace
        self._file_suggester.invalidate_cache()
