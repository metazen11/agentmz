#!/usr/bin/env python3
"""Forge CLI - Launch TUI, REPL, or run single prompt."""
import os
import readline
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = typer.Typer(
    name="forge",
    help="Forge TUI - Local-first agentic coding environment",
    add_completion=False,
)


class ForgeREPL:
    """Simple readline-based REPL with same commands as TUI."""

    def __init__(
        self,
        workspace: str,
        model: str,
        ollama_url: str,
        max_iters: int,
        timeout: int,
    ):
        self.workspace = self._resolve_workspace(workspace)
        self.model = model
        self.ollama_url = ollama_url
        self.max_iters = max_iters
        self.timeout = timeout
        self.history: list[str] = []
        self._setup_readline()

    def _resolve_workspace(self, workspace: str) -> str:
        """Resolve workspace to absolute path."""
        if not workspace:
            return os.getcwd()
        if os.path.isabs(workspace):
            return workspace
        if os.path.isdir(workspace):
            return os.path.abspath(workspace)
        # Check workspaces/ subdirectory
        ws_path = os.path.join(os.getcwd(), "workspaces", workspace)
        if os.path.isdir(ws_path):
            return ws_path
        return os.path.abspath(workspace)

    def _setup_readline(self):
        """Configure readline with history and completion."""
        # History file
        history_file = os.path.expanduser("~/.forge_history")
        try:
            readline.read_history_file(history_file)
        except FileNotFoundError:
            pass
        import atexit
        atexit.register(readline.write_history_file, history_file)

        # Tab completion for files
        readline.set_completer(self._complete)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n@")

    def _complete(self, text: str, state: int) -> Optional[str]:
        """Complete file paths after @."""
        if "@" in readline.get_line_buffer():
            # Get text after last @
            line = readline.get_line_buffer()
            at_pos = line.rfind("@")
            partial = line[at_pos + 1:]

            matches = self._get_file_matches(partial)
            if state < len(matches):
                return matches[state]
        return None

    def _get_file_matches(self, partial: str) -> list[str]:
        """Get matching files in workspace."""
        try:
            workspace_path = Path(self.workspace)
            ignore_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__"}
            matches = []

            for item in workspace_path.rglob("*"):
                if any(p in ignore_dirs for p in item.parts):
                    continue
                relpath = str(item.relative_to(workspace_path))
                if partial.lower() in relpath.lower():
                    matches.append(relpath)
                if len(matches) >= 20:
                    break
            return sorted(matches)
        except Exception:
            return []

    def _handle_builtin(self, line: str) -> Optional[str]:
        """Handle built-in commands. Returns None if not a builtin."""
        parts = line.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip().strip("\"'") if len(parts) > 1 else ""

        if cmd == "cd":
            return self._cmd_cd(arg)
        elif cmd == "pwd":
            return self.workspace
        elif cmd == "ls":
            return self._cmd_ls(arg)
        elif cmd in ("clear", "cls"):
            try:
                if os.name == "nt":
                    subprocess.run(["cmd.exe", "/c", "cls"], check=False)
                else:
                    subprocess.run(["clear"], check=False)
            except Exception:
                pass
            return ""
        elif cmd == "model":
            if arg:
                self.model = arg
                return f"Model set to: {arg}"
            return f"Current model: {self.model}"
        elif cmd in ("help", "?"):
            return self._cmd_help()
        elif cmd in ("exit", "quit", "q"):
            raise EOFError()
        elif cmd in ("cp", "mv", "mkdir", "touch", "rm", "cat", "head", "tail", "grep", "curl", "git"):
            return self._cmd_shell(line)
        elif cmd == "/config" or cmd == "config":
            from forge.config import handle_config_command
            result = handle_config_command(arg)
            # If model changed, update REPL state
            if "Model set to:" in result:
                self.model = arg.split()[0] if arg else self.model
            return result
        return None

    def _cmd_cd(self, path: str) -> str:
        """Change workspace directory."""
        if not path:
            return f"Current workspace: {self.workspace}"
        if path.startswith("~"):
            path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(self.workspace, path))
        if os.path.isdir(path):
            self.workspace = path
            return f"Workspace: {path}"
        return f"Not a directory: {path}"

    def _cmd_ls(self, path: str) -> str:
        """List files."""
        target = os.path.join(self.workspace, path) if path else self.workspace
        if not os.path.isdir(target):
            return f"Not a directory: {target}"
        try:
            entries = sorted(os.listdir(target))
            lines = []
            for entry in entries[:50]:
                full = os.path.join(target, entry)
                if os.path.isdir(full):
                    lines.append(f"{entry}/")
                else:
                    lines.append(entry)
            if len(entries) > 50:
                lines.append(f"... and {len(entries) - 50} more")
            return "\n".join(lines)
        except OSError as e:
            return f"Error: {e}"

    def _cmd_shell(self, cmd: str) -> str:
        """Run shell command in workspace."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += result.stderr
            if result.returncode != 0 and not result.stderr:
                output += f"Exit code: {result.returncode}"
            return output.strip() or "OK"
        except subprocess.TimeoutExpired:
            return "Command timed out (30s)"
        except Exception as e:
            return f"Error: {e}"

    def _cmd_help(self) -> str:
        """Show help."""
        return """Built-in commands (instant, no LLM):
  cd <path>     Change workspace directory
  pwd           Show current workspace
  ls [path]     List files
  model [name]  Show/set model
  /config       Show/edit settings
  history       Show conversation history
  stats         Show token usage
  reset         Reset session
  clear         Clear screen
  help          Show this help
  exit/quit     Exit REPL

Config commands:
  /config                 Show all settings
  /config model NAME      Set model
  /config list-models     Discover from Ollama
  /config workspace DIR   Set workspace

Shell commands (run directly):
  cp, mv, rm    File operations
  mkdir, touch  Create dirs/files
  cat, head, tail  View files
  grep <pattern>  Search in files
  git <cmd>     Git commands
  curl <url>    HTTP requests

Everything else goes to the LLM.
Use @ for file completion (e.g., @src/main.py)"""

    def run(self):
        """Run the REPL with session tracking."""
        from forge.agent.runner import run_with_session
        from forge.agent.session import Session

        # Initialize session with conversation history
        self.session = Session(model=self.model, max_history=10)

        self._print_header()

        while True:
            try:
                # Show prompt with stats
                stats = self.session.stats.to_status()
                line = input(f"forge [{stats}]> ").strip()
                if not line:
                    continue

                # Try built-in first
                result = self._handle_builtin(line)
                if result is not None:
                    if result:
                        print(result)
                    continue

                # Special commands for session management
                if line.lower() == "history":
                    print(self.session.get_history_summary(last_n=10))
                    continue
                if line.lower() == "reset":
                    self.session.reset()
                    print("Session reset.")
                    continue
                if line.lower() == "stats":
                    stats = self.session.stats
                    print(f"Turns: {stats.turn_count}")
                    print(f"Tokens: {stats.total_tokens} / {stats.max_context} ({stats.context_pct:.1f}%)")
                    print(f"Prompt tokens: {stats.prompt_tokens}")
                    print(f"Completion tokens: {stats.completion_tokens}")
                    print(f"Elapsed: {stats.elapsed_time:.1f}s")
                    continue

                # Strip @ from file paths before sending
                import re
                processed = re.sub(
                    r'@([a-zA-Z0-9_./-]+)',
                    lambda m: m.group(1) if '/' in m.group(1) or m.group(1).startswith('.') or
                    re.search(r'\.(py|js|ts|html|css|json|md|txt|yaml|yml|toml|sh)$', m.group(1)) else '@' + m.group(1),
                    line
                )

                # Add to session history
                self.session.add_user_message(processed)

                print("Thinking...")
                result = run_with_session(
                    session=self.session,
                    prompt=processed,
                    workspace=self.workspace,
                    ollama_url=self.ollama_url,
                    max_iters=self.max_iters,
                    timeout=self.timeout,
                )

                # Add response to session
                self.session.add_assistant_message(result)

                print(result)
                print()

            except EOFError:
                print("\nBye!")
                break
            except KeyboardInterrupt:
                print("\n(Ctrl+C to cancel, 'exit' to quit)")
                continue

    def _print_header(self):
        """Print session header."""
        print(f"\n{'='*60}")
        print(f"FORGE | Workspace: {self.workspace} | Model: {self.model}")
        print(f"Context: {self.session.stats.max_context} tokens")
        print(f"{'='*60}")
        print("Commands: help, history, stats, reset, exit")
        print()


@app.command()
def main(
    tui: bool = typer.Option(
        False,
        "--tui", "-t",
        help="Launch TUI mode (Textual app)",
    ),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt", "-p",
        help="Single prompt (one-off mode)",
    ),
    prompt_file: Optional[str] = typer.Option(
        None,
        "--file", "-f",
        help="Read prompt from file",
    ),
    workspace: str = typer.Option(
        "poc",
        "--workspace", "-w",
        help="Workspace name or path",
        envvar="FORGE_WORKSPACE",
    ),
    model: str = typer.Option(
        "gemma3:4b",
        "--model", "-m",
        help="Ollama model to use",
        envvar="FORGE_MODEL",
    ),
    ollama_url: str = typer.Option(
        "http://localhost:11435",
        "--ollama",
        help="Ollama API base URL",
        envvar="FORGE_OLLAMA_BASE",
    ),
    max_iters: int = typer.Option(
        6,
        "--max-iters",
        help="Maximum agent iterations",
        envvar="FORGE_MAX_ITERS",
    ),
    timeout: int = typer.Option(
        120,
        "--timeout",
        help="Timeout per LLM call (seconds)",
        envvar="FORGE_INVOKE_TIMEOUT",
    ),
):
    """
    Forge - Local-first agentic coding environment.

    Examples:

        forge                           # Interactive CLI
        forge -t                        # TUI mode
        forge -p "Create hello.html"    # One-off prompt
        forge -f task.txt -w myproject  # Prompt from file
    """
    # Determine prompt source
    actual_prompt = None
    if prompt_file:
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                actual_prompt = f.read().strip()
        except FileNotFoundError:
            typer.echo(f"Error: File not found: {prompt_file}", err=True)
            raise typer.Exit(1)
    elif prompt:
        actual_prompt = prompt

    # If prompt provided, run one-off mode
    if actual_prompt:
        from forge.agent.runner import run_once

        result = run_once(
            prompt=actual_prompt,
            workspace=workspace,
            model=model,
            ollama_url=ollama_url,
            max_iters=max_iters,
            timeout=timeout,
        )
        typer.echo(result)
    elif tui:
        # TUI mode (Textual app)
        from forge.app import ForgeApp

        forge_app = ForgeApp(
            workspace=workspace,
            model=model,
            ollama_url=ollama_url,
            max_iters=max_iters,
            timeout=timeout,
        )
        forge_app.run()
    else:
        # Default: Interactive CLI mode
        repl = ForgeREPL(
            workspace=workspace,
            model=model,
            ollama_url=ollama_url,
            max_iters=max_iters,
            timeout=timeout,
        )
        repl.run()


if __name__ == "__main__":
    app()
