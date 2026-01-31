"""Forge TUI - Main Textual Application."""
import os
import subprocess
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Input, Static
from textual.worker import Worker, get_current_worker

from forge.widgets.chat_display import ChatDisplay
from forge.widgets.file_autocomplete import FileAutoComplete, FileInput
from forge.widgets.status_bar import StatusBar


class ForgeApp(App):
    """Forge TUI - Local-first agentic coding environment."""

    CSS_PATH = "forge.tcss"
    TITLE = "Forge"
    ENABLE_COMMAND_PALETTE = True  # Show palette with ctrl+p

    BINDINGS = [
        Binding("ctrl+enter", "submit", "Submit", show=True),
        Binding("ctrl+y", "copy", "Copy", show=True),
        Binding("ctrl+v", "paste", "Paste", show=True),
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("f1", "menu", "Help", show=True),
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
        self.last_response: str = ""  # For clipboard copy

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield StatusBar(
            workspace=self.workspace,
            model=self.model,
            id="status-bar",
        )
        yield Container(
            ChatDisplay(id="chat"),
            id="chat-container",
        )
        prompt_input = FileInput(
            workspace=self.workspace,
            placeholder="Enter your prompt... (@ for files)",
            id="prompt-input",
        )
        yield prompt_input
        yield FileAutoComplete(target=prompt_input, workspace=self.workspace)
        yield Footer()

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#prompt-input", FileInput).focus()
        self.query_one("#chat", ChatDisplay).write(
            "[dim]Ready. Ctrl+Enter to submit, @ for file completion.[/dim]\n"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle prompt submission."""
        prompt = event.value.strip()
        if not prompt:
            return

        # Clear input IMMEDIATELY for responsiveness
        event.input.value = ""

        # Add to history
        self.history.append(prompt)
        self.history_index = len(self.history)

        chat = self.query_one("#chat", ChatDisplay)
        chat.write(f"\n[bold cyan]> {prompt}[/bold cyan]\n")

        # Try deterministic commands first (no LLM needed)
        if self._handle_builtin_command(prompt):
            return

        # Display status for LLM call
        status = self.query_one("#status-bar", StatusBar)
        chat.write("[dim]Sending...[/dim]")
        status.set_status("Sending...")
        status.set_running(True)

        # Force refresh before async work starts
        self.refresh()

        # Run agent in background
        self.run_agent(prompt)

    def _handle_builtin_command(self, prompt: str) -> bool:
        """Handle deterministic commands without LLM. Returns True if handled."""
        chat = self.query_one("#chat", ChatDisplay)
        status = self.query_one("#status-bar", StatusBar)
        parts = prompt.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip().strip('"\'') if len(parts) > 1 else ""

        if cmd == "cd":
            return self._cmd_cd(arg, chat, status)
        elif cmd == "pwd":
            chat.write(f"[green]{self.workspace}[/green]\n")
            return True
        elif cmd == "ls":
            return self._cmd_ls(arg, chat)
        elif cmd in ("clear", "cls"):
            self.action_clear()
            return True
        elif cmd == "help" or cmd == "?":
            self._cmd_help(chat)
            return True
        elif cmd == "model":
            if arg:
                self.model = arg
                status.set_model(arg)
                chat.write(f"[green]Model set to: {arg}[/green]\n")
            else:
                chat.write(f"[green]Current model: {self.model}[/green]\n")
            return True
        elif cmd in ("cp", "mv", "mkdir", "touch", "rm", "cat", "head", "tail", "grep", "curl", "git"):
            # Shell commands - run directly
            return self._cmd_shell(prompt, chat)
        elif cmd == "/config" or cmd == "config":
            from forge.config import handle_config_command
            result = handle_config_command(arg)
            chat.write(f"[green]{result}[/green]\n")
            # If model changed, update TUI state
            if "Model set to:" in result and arg:
                model_name = arg.split()[0]
                self.model = model_name
                status.set_model(model_name)
            return True

        return False

    def _cmd_shell(self, cmd: str, chat) -> bool:
        """Run shell command directly in workspace."""
        import subprocess
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                chat.write(f"{result.stdout}")
            if result.stderr:
                chat.write(f"[red]{result.stderr}[/red]")
            if result.returncode != 0 and not result.stderr:
                chat.write(f"[red]Exit code: {result.returncode}[/red]\n")
            elif result.returncode == 0 and not result.stdout and not result.stderr:
                chat.write("[green]OK[/green]\n")
        except subprocess.TimeoutExpired:
            chat.write("[red]Command timed out (30s)[/red]\n")
        except Exception as e:
            chat.write(f"[red]Error: {e}[/red]\n")
        return True

    def _cmd_cd(self, path: str, chat, status) -> bool:
        """Change workspace directory."""
        if not path:
            chat.write(f"[green]Current workspace: {self.workspace}[/green]\n")
            return True

        # Resolve path
        if path.startswith("~"):
            path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(self.workspace, path))

        if os.path.isdir(path):
            self.workspace = path
            status.set_workspace(path)
            # Update autocomplete
            prompt_input = self.query_one("#prompt-input", FileInput)
            prompt_input.set_workspace(path)
            chat.write(f"[green]Workspace: {path}[/green]\n")
        else:
            chat.write(f"[red]Not a directory: {path}[/red]\n")
        return True

    def _cmd_ls(self, path: str, chat) -> bool:
        """List files in workspace."""
        target = os.path.join(self.workspace, path) if path else self.workspace
        if not os.path.isdir(target):
            chat.write(f"[red]Not a directory: {target}[/red]\n")
            return True

        try:
            entries = sorted(os.listdir(target))
            for entry in entries[:50]:
                full = os.path.join(target, entry)
                if os.path.isdir(full):
                    chat.write(f"[blue]{entry}/[/blue]\n")
                else:
                    chat.write(f"{entry}\n")
            if len(entries) > 50:
                chat.write(f"[dim]... and {len(entries) - 50} more[/dim]\n")
        except OSError as e:
            chat.write(f"[red]Error: {e}[/red]\n")
        return True

    def _cmd_help(self, chat) -> None:
        """Show built-in commands."""
        chat.write("[bold]Built-in commands (instant, no LLM):[/bold]\n")
        chat.write("  [cyan]cd <path>[/cyan]     Change workspace directory\n")
        chat.write("  [cyan]pwd[/cyan]           Show current workspace\n")
        chat.write("  [cyan]ls [path][/cyan]     List files\n")
        chat.write("  [cyan]model [name][/cyan]  Show/set model\n")
        chat.write("  [cyan]/config[/cyan]       Show/edit settings\n")
        chat.write("  [cyan]clear[/cyan]         Clear chat\n")
        chat.write("  [cyan]help[/cyan]          Show this help\n")
        chat.write("\n[bold]/config commands:[/bold]\n")
        chat.write("  [cyan]/config[/cyan]                 Show all settings\n")
        chat.write("  [cyan]/config model NAME[/cyan]      Set model\n")
        chat.write("  [cyan]/config list-models[/cyan]     Discover from Ollama\n")
        chat.write("  [cyan]/config workspace DIR[/cyan]   Set workspace\n")
        chat.write("\n[bold]Shell commands (run directly):[/bold]\n")
        chat.write("  [cyan]cp, mv, rm[/cyan]    File operations\n")
        chat.write("  [cyan]mkdir, touch[/cyan]  Create dirs/files\n")
        chat.write("  [cyan]cat, head, tail[/cyan] View files\n")
        chat.write("  [cyan]grep <pattern>[/cyan] Search in files\n")
        chat.write("  [cyan]git <cmd>[/cyan]     Git commands\n")
        chat.write("  [cyan]curl <url>[/cyan]    HTTP requests\n")
        chat.write("\n[dim]Everything else goes to the LLM.[/dim]\n")

    def run_agent(self, prompt: str) -> None:
        """Run the agent in a background worker."""
        @self.call_later
        def start_worker():
            self.current_worker = self.run_worker(
                self._run_agent_task(prompt),
                name="agent",
                exit_on_error=False,
            )

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
                    self.last_response = content  # Store for clipboard
                    chat.write(f"\n[green]{content}[/green]\n")
                elif event_type == "error":
                    msg = event.get("message", "Unknown error")
                    chat.write(f"\n[red]Error: {msg}[/red]\n")
        except Exception as e:
            chat.write(f"\n[red]Error: {e}[/red]\n")
        finally:
            status.set_running(False)
            status.set_status("")

    def action_submit(self) -> None:
        """Submit the current prompt (handled by Input widget)."""
        # This is here to show the binding in footer; actual submit is handled by Input.Submitted
        pass

    def _get_clipboard_commands(self) -> tuple[list[str], list[str]]:
        """Get platform-specific clipboard commands (copy_cmd, paste_cmd)."""
        import platform
        system = platform.system()

        if system == "Darwin":  # macOS
            return (["pbcopy"], ["pbpaste"])
        elif system == "Linux":
            # Check if WSL
            try:
                with open("/proc/version", "r") as f:
                    if "microsoft" in f.read().lower():
                        return (["clip.exe"], ["powershell.exe", "-command", "Get-Clipboard"])
            except:
                pass
            # Native Linux - try xclip
            return (["xclip", "-selection", "clipboard"], ["xclip", "-selection", "clipboard", "-o"])
        else:  # Windows native (unlikely in terminal)
            return (["clip"], ["powershell", "-command", "Get-Clipboard"])

    def action_copy(self) -> None:
        """Copy full conversation to clipboard."""
        chat = self.query_one("#chat", ChatDisplay)
        content = chat.get_plain_text()
        if not content.strip():
            self.notify("Nothing to copy")
            return
        try:
            copy_cmd, _ = self._get_clipboard_commands()
            process = subprocess.Popen(
                copy_cmd,
                stdin=subprocess.PIPE,
                text=True,
            )
            process.communicate(input=content)
            self.notify(f"Copied {len(content)} chars")
        except Exception as e:
            self.notify(f"Copy failed: {e}")

    def action_paste(self) -> None:
        """Paste from clipboard into input."""
        try:
            _, paste_cmd = self._get_clipboard_commands()
            result = subprocess.run(
                paste_cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                text = result.stdout.strip()
                prompt_input = self.query_one("#prompt-input", FileInput)
                prompt_input.value = prompt_input.value + text
                self.notify(f"Pasted {len(text)} chars")
            else:
                self.notify("Clipboard empty")
        except Exception as e:
            self.notify(f"Paste failed: {e}")

    def action_menu(self) -> None:
        """Show menu options."""
        self.notify("Ctrl+Y Copy | Ctrl+V Paste | Ctrl+L Clear | Up/Down History")

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
            prompt_input = self.query_one("#prompt-input", FileInput)
            prompt_input.value = self.history[self.history_index]

    def action_history_next(self) -> None:
        """Navigate to next history item."""
        if not self.history:
            return
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            prompt_input = self.query_one("#prompt-input", FileInput)
            prompt_input.value = self.history[self.history_index]
        elif self.history_index == len(self.history) - 1:
            self.history_index = len(self.history)
            prompt_input = self.query_one("#prompt-input", FileInput)
            prompt_input.value = ""
