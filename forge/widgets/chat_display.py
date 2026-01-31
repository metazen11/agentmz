"""Chat display widget for Forge TUI."""
from textual.widgets import RichLog


class ChatDisplay(RichLog):
    """Scrollable chat display with Rich markdown support."""

    DEFAULT_CSS = """
    ChatDisplay {
        background: $surface;
        padding: 1;
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            **kwargs,
        )

    def clear(self) -> None:
        """Clear all content."""
        super().clear()

    def get_plain_text(self) -> str:
        """Return the full chat content as plain text."""
        # Strip trailing padding to avoid excessive whitespace.
        return "\n".join(line.text.rstrip() for line in self.lines)
