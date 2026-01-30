"""Forge TUI - Main Textual Application."""
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Input, Static
from textual.worker import Worker, get_current_worker

from forge.widgets.chat_display import ChatDisplay
from forge.widgets.status_bar import StatusBar


class ForgeApp(App):
    """Forge TUI - Local-first agentic coding environment."""

    CSS_PATH = "forge.tcss"
    TITLE = "Forge"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "history_prev", "Previous", show=False),
        Binding("down", "history_next", "Next", show=False),
    ]

    def __init__(
        self,
        workspace: str = "poc",
        model: str = "gemma3:4b",
        ollama_url: str = "http://localhost:11435",
        max_iters: int = 6,
        timeout: int = 120,
    ):
        super().__init__()
        self.workspace = workspace
        self.model = model
        self.ollama_url = ollama_url
        self.max_iters = max_iters
        self.timeout = timeout
        self.history: list[str] = []
        self.history_index = -1
        self.current_worker: Worker | None = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        yield StatusBar(
            workspace=self.workspace,
            model=self.model,
            id="status-bar",
        )
        yield Container(
            ChatDisplay(id="chat"),
            id="chat-container",
        )
        yield Input(placeholder="Enter your prompt...", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#prompt-input", Input).focus()
        self.query_one("#chat", ChatDisplay).write(
            f"[dim]Forge ready. Workspace: {self.workspace}, Model: {self.model}[/dim]\n"
            "[dim]Type a prompt and press Enter. Ctrl+C to quit.[/dim]\n"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle prompt submission."""
        prompt = event.value.strip()
        if not prompt:
            return

        # Add to history
        self.history.append(prompt)
        self.history_index = len(self.history)

        # Clear input
        event.input.value = ""

        # Display prompt
        chat = self.query_one("#chat", ChatDisplay)
        chat.write(f"\n[bold cyan]> {prompt}[/bold cyan]\n")

        # Run agent in background
        self.run_agent(prompt)

    def run_agent(self, prompt: str) -> None:
        """Run the agent in a background worker."""
        from forge.agent.runner import run_streaming

        chat = self.query_one("#chat", ChatDisplay)
        status = self.query_one("#status-bar", StatusBar)

        @self.call_later
        def start_worker():
            self.current_worker = self.run_worker(
                self._run_agent_task(prompt),
                name="agent",
                exit_on_error=False,
            )
            status.set_running(True)

    async def _run_agent_task(self, prompt: str) -> None:
        """Background task for running agent."""
        from forge.agent.runner import run_streaming

        chat = self.query_one("#chat", ChatDisplay)
        status = self.query_one("#status-bar", StatusBar)

        try:
            for event in run_streaming(
                prompt=prompt,
                workspace=self.workspace,
                model=self.model,
                ollama_url=self.ollama_url,
                max_iters=self.max_iters,
                timeout=self.timeout,
            ):
                worker = get_current_worker()
                if worker.is_cancelled:
                    chat.write("\n[yellow]Cancelled.[/yellow]\n")
                    break

                event_type = event.get("type")
                if event_type == "status":
                    status.set_status(event.get("message", ""))
                elif event_type == "chunk":
                    chat.write(event.get("content", ""))
                elif event_type == "tool_call":
                    name = event.get("name", "tool")
                    chat.write(f"\n[dim]Running {name}...[/dim]")
                elif event_type == "tool_result":
                    chat.write(" [green]done[/green]\n")
                elif event_type == "done":
                    content = event.get("content", "")
                    chat.write(f"\n[green]{content}[/green]\n")
                elif event_type == "error":
                    msg = event.get("message", "Unknown error")
                    chat.write(f"\n[red]Error: {msg}[/red]\n")
        except Exception as e:
            chat.write(f"\n[red]Error: {e}[/red]\n")
        finally:
            status.set_running(False)
            status.set_status("")

    def action_clear(self) -> None:
        """Clear the chat display."""
        chat = self.query_one("#chat", ChatDisplay)
        chat.clear()
        chat.write("[dim]Chat cleared.[/dim]\n")

    def action_cancel(self) -> None:
        """Cancel current operation."""
        if self.current_worker and not self.current_worker.is_finished:
            self.current_worker.cancel()

    def action_history_prev(self) -> None:
        """Navigate to previous history item."""
        if not self.history:
            return
        if self.history_index > 0:
            self.history_index -= 1
            prompt_input = self.query_one("#prompt-input", Input)
            prompt_input.value = self.history[self.history_index]

    def action_history_next(self) -> None:
        """Navigate to next history item."""
        if not self.history:
            return
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            prompt_input = self.query_one("#prompt-input", Input)
            prompt_input.value = self.history[self.history_index]
        elif self.history_index == len(self.history) - 1:
            self.history_index = len(self.history)
            prompt_input = self.query_one("#prompt-input", Input)
            prompt_input.value = ""
