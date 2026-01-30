"""File autocomplete widget for @ mentions using textual-autocomplete."""
import os
from pathlib import Path

from textual.widgets import Input

try:
    from textual_autocomplete import AutoComplete, DropdownItem
    HAS_AUTOCOMPLETE = True
except ImportError:
    HAS_AUTOCOMPLETE = False
    AutoComplete = None
    DropdownItem = None


class FileAutoComplete(AutoComplete if HAS_AUTOCOMPLETE else object):
    """Autocomplete dropdown that triggers on @ for file selection."""

    def __init__(self, target: Input, workspace: str = ".", **kwargs):
        if not HAS_AUTOCOMPLETE:
            raise ImportError("textual-autocomplete required: pip install textual-autocomplete")
        super().__init__(target=target, **kwargs)
        self.workspace = workspace
        self._file_cache: list[str] | None = None

    def _scan_files(self, max_files: int = 200) -> list[str]:
        """Scan workspace for files."""
        if self._file_cache is not None:
            return self._file_cache

        files = []
        workspace_path = Path(self.workspace)

        if not workspace_path.exists():
            return []

        ignore_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".cache", ".aider"}

        for root, dirs, filenames in os.walk(workspace_path):
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
        """Clear file cache to force rescan."""
        self._file_cache = None

    def get_search_string(self, target_state) -> str:
        """Extract the search string after @."""
        # target_state is a TargetState namedtuple with text and cursor_position
        value = target_state.text if hasattr(target_state, 'text') else str(target_state)
        at_pos = value.rfind("@")
        if at_pos == -1:
            return ""
        partial = value[at_pos + 1:]
        # Don't search if there's a space (already completed)
        if " " in partial:
            return ""
        return partial

    def get_candidates(self, search_string: str) -> list[DropdownItem]:
        """Return matching file candidates."""
        if not search_string and "@" not in (self.target.value or ""):
            return []

        files = self._scan_files()
        search_lower = search_string.lower()

        matches = []
        for filepath in files:
            filepath_lower = filepath.lower()
            # Fuzzy match: search string anywhere in path
            if search_lower in filepath_lower or filepath_lower.startswith(search_lower):
                matches.append(DropdownItem(main=filepath))
            if len(matches) >= 15:  # Limit dropdown size
                break

        return matches

    def apply_completion(self, target_state, item: DropdownItem) -> str:
        """Insert the selected file path after @."""
        # target_state is a TargetState namedtuple with text and cursor_position
        value = target_state.text if hasattr(target_state, 'text') else str(target_state)
        at_pos = value.rfind("@")
        if at_pos == -1:
            return value + item.main

        # Replace @partial with @filepath
        prefix = value[:at_pos + 1]  # Keep the @
        return prefix + item.main + " "


# Keep FileInput for backwards compatibility but use the dropdown
class FileInput(Input):
    """Input widget - use with FileAutoComplete for @ file completion."""

    def __init__(self, workspace: str = ".", *args, **kwargs):
        self.workspace = workspace
        # Remove suggester if passed - we'll use FileAutoComplete dropdown instead
        kwargs.pop("suggester", None)
        super().__init__(*args, **kwargs)

    def set_workspace(self, workspace: str) -> None:
        """Update workspace for file suggestions."""
        self.workspace = workspace
