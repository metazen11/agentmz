#!/usr/bin/env python3
"""Forge CLI - Launch TUI, REPL, or run single prompt."""
import os
import readline
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from forge.workspaces import (
    add_workspace,
    find_workspace,
    list_workspaces,
    remove_workspace,
    resolve_workspace,
    set_default_workspace,
)

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = typer.Typer(
    name="forge",
    help="Forge - Local-first agentic coding environment",
    add_completion=False,
)


# Workspace registry subcommands
workspaces_app = typer.Typer(help="Workspace registry and router")
app.add_typer(workspaces_app, name="workspaces")

# Memory subcommands (knowledge base)
memory_app = typer.Typer(help="Knowledge memory management")
app.add_typer(memory_app, name="memory")

# Agent memory subcommands (observations)
from forge.agentmem.cli import app as mem_app
app.add_typer(mem_app, name="mem")


@memory_app.command("store")
def memory_store(
    content: str = typer.Argument(..., help="Content to store"),
    summary: Optional[str] = typer.Option(None, "--summary", "-s", help="Summary of content"),
    file_path: Optional[str] = typer.Option(None, "--file", "-f", help="Associated file path"),
    content_type: str = typer.Option("doc", "--type", "-t", help="Content type (doc, code, solution, architecture)"),
    project_id: int = typer.Option(1, "--project", "-p", help="Project ID", envvar="FORGE_PROJECT_ID"),
):
    """Store knowledge in memory with embeddings."""
    try:
        from forge.memory.store import ProjectMemory
        from forge.hooks.auto_embed import generate_embedding_sync

        memory = ProjectMemory(project_id=project_id)

        # Generate embedding
        typer.echo("Generating embedding...")
        embedding = generate_embedding_sync(content)

        if not embedding:
            typer.echo("Warning: Could not generate embedding, storing without vector", err=True)

        result = memory.store(
            content_type=content_type,
            content=content,
            summary=summary or content[:100],
            file_path=file_path,
            embedding=embedding,
        )

        if result.get("success"):
            typer.echo(f"Stored: id={result.get('id')} type={content_type}")
        else:
            typer.echo(f"Error: {result.get('error')}", err=True)
            raise typer.Exit(1)
    except ImportError as e:
        typer.echo(f"Error: Missing dependency - {e}", err=True)
        raise typer.Exit(1)


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query"),
    mode: str = typer.Option("hybrid", "--mode", "-m", help="Search mode: text, embedding, hybrid"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
    project_id: int = typer.Option(1, "--project", "-p", help="Project ID", envvar="FORGE_PROJECT_ID"),
):
    """Search knowledge memory."""
    try:
        from forge.memory.store import ProjectMemory
        from forge.hooks.auto_embed import generate_embedding_sync

        memory = ProjectMemory(project_id=project_id)

        # Generate embedding for hybrid/embedding mode
        embedding = None
        if mode in ("hybrid", "embedding"):
            embedding = generate_embedding_sync(query)

        result = memory.search(
            query=query,
            embedding=embedding,
            mode=mode,
            limit=limit,
        )

        if result.get("success"):
            typer.echo(f"Found {result.get('count')} results (mode={result.get('mode')}):\n")
            for r in result.get("results", []):
                typer.echo(f"  [{r['score']:.3f}] {r.get('file_path') or r['content_type']}")
                typer.echo(f"    {r['content'][:100]}...")
                typer.echo()
        else:
            typer.echo(f"Error: {result.get('error')}", err=True)
            raise typer.Exit(1)
    except ImportError as e:
        typer.echo(f"Error: Missing dependency - {e}", err=True)
        raise typer.Exit(1)


@memory_app.command("stats")
def memory_stats(
    project_id: int = typer.Option(1, "--project", "-p", help="Project ID", envvar="FORGE_PROJECT_ID"),
):
    """Show memory statistics."""
    try:
        from forge.memory.store import ProjectMemory

        memory = ProjectMemory(project_id=project_id)
        result = memory.stats()

        if result.get("success"):
            stats = result.get("stats", {})
            typer.echo(f"Project {project_id} Knowledge Base:")
            typer.echo(f"  Total entries: {stats.get('total', 0)}")
            typer.echo(f"  By type:")
            for ctype, count in stats.get("by_type", {}).items():
                typer.echo(f"    {ctype}: {count}")
        else:
            typer.echo(f"Error: {result.get('error')}", err=True)
            raise typer.Exit(1)
    except ImportError as e:
        typer.echo(f"Error: Missing dependency - {e}", err=True)
        raise typer.Exit(1)


@workspaces_app.command("list")
def workspaces_list():
    """List registered workspaces."""
    items = list_workspaces()
    if not items:
        typer.echo("No workspaces registered.")
        raise typer.Exit(0)
    for ws in items:
        tags = ",".join(ws.tags) if ws.tags else "-"
        sigs = ",".join(ws.repo_signatures) if ws.repo_signatures else "-"
        proj = ws.project_id if ws.project_id is not None else "-"
        last_used = ws.last_used or "-"
        typer.echo(f"{ws.id} | {ws.name} | {ws.root}")
        typer.echo(f"  tags={tags}  signatures={sigs}  project_id={proj}  last_used={last_used}")


@workspaces_app.command("add")
def workspaces_add(
    name: str = typer.Option(..., "--name", help="Workspace name"),
    root: str = typer.Option(..., "--root", help="Workspace root path"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Comma-separated tags"),
    signatures: Optional[str] = typer.Option(None, "--signatures", help="Comma-separated repo signatures"),
    project_id: Optional[int] = typer.Option(None, "--project-id", help="Associated project ID"),
    default: bool = typer.Option(False, "--default", help="Set as default workspace"),
):
    """Add or update a workspace."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    sig_list = [s.strip() for s in signatures.split(",")] if signatures else []
    ws = add_workspace(
        name=name,
        root=root,
        tags=tag_list,
        repo_signatures=sig_list,
        project_id=project_id,
        set_default=default,
    )
    typer.echo(f"Saved workspace: {ws.id} ({ws.name}) -> {ws.root}")


@workspaces_app.command("remove")
def workspaces_remove(key: str = typer.Argument(..., help="Workspace id or name")):
    """Remove a workspace."""
    if remove_workspace(key):
        typer.echo(f"Removed workspace: {key}")
    else:
        typer.echo(f"Workspace not found: {key}")
        raise typer.Exit(1)


@workspaces_app.command("set-default")
def workspaces_set_default(key: str = typer.Argument(..., help="Workspace id or name")):
    """Set the default workspace."""
    if set_default_workspace(key):
        typer.echo(f"Default workspace set: {key}")
    else:
        typer.echo(f"Workspace not found: {key}")
        raise typer.Exit(1)


@workspaces_app.command("resolve")
def workspaces_resolve(
    hint: Optional[str] = typer.Option(None, "--hint", help="Hint for router (tag/name/signature)"),
    explicit: Optional[str] = typer.Option(None, "--explicit", help="Explicit workspace id/name/path"),
):
    """Resolve a workspace from current context."""
    result = resolve_workspace(
        cwd=os.getcwd(),
        hint=hint,
        explicit=explicit,
    )
    typer.echo(f"{result.get('root')}")
    typer.echo(f"id={result.get('id')} name={result.get('name')} project_id={result.get('project_id')}")
    typer.echo(f"score={result.get('score')} source={result.get('source')} reasons={','.join(result.get('reasons') or [])}")


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
        "auto",
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

    # Resolve workspace (by registry or router)
    if workspace and workspace.lower() == "auto":
        hint = os.environ.get("FORGE_WORKSPACE_HINT")
        resolved = resolve_workspace(cwd=os.getcwd(), hint=hint, explicit=None)
        workspace = resolved.get("root") or workspace
        if resolved.get("id"):
            os.environ["FORGE_WORKSPACE_ID"] = str(resolved["id"])
        if resolved.get("project_id") is not None:
            os.environ["FORGE_PROJECT_ID"] = str(resolved["project_id"])
    else:
        ws_entry = find_workspace(workspace)
        if ws_entry:
            workspace = ws_entry.root
            os.environ["FORGE_WORKSPACE_ID"] = str(ws_entry.id)
            if ws_entry.project_id is not None:
                os.environ["FORGE_PROJECT_ID"] = str(ws_entry.project_id)

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
