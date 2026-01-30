"""Status bar widget for Forge TUI."""
from textual.widgets import Static
from textual.reactive import reactive


class StatusBar(Static):
    """Status bar showing workspace, model, and current status."""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    StatusBar.running {
        background: $warning-darken-2;
    }
    """

    workspace: reactive[str] = reactive("poc")
    model: reactive[str] = reactive("gemma3:4b")
    status: reactive[str] = reactive("")
    running: reactive[bool] = reactive(False)

    def __init__(
        self,
        workspace: str = "poc",
        model: str = "gemma3:4b",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.workspace = workspace
        self.model = model

    def render(self) -> str:
        """Render the status bar."""
        parts = [
            f"[bold]Workspace:[/bold] {self.workspace}",
            f"[bold]Model:[/bold] {self.model}",
        ]
        if self.status:
            parts.append(f"[dim]{self.status}[/dim]")
        if self.running:
            parts.append("[yellow]Running...[/yellow]")
        return " | ".join(parts)

    def set_status(self, status: str) -> None:
        """Update status message."""
        self.status = status
        self.refresh()

    def set_running(self, running: bool) -> None:
        """Update running state."""
        self.running = running
        if running:
            self.add_class("running")
        else:
            self.remove_class("running")
        self.refresh()

    def set_model(self, model: str) -> None:
        """Update model."""
        self.model = model
        self.refresh()

    def set_workspace(self, workspace: str) -> None:
        """Update workspace."""
        self.workspace = workspace
        self.refresh()
