#!/usr/bin/env python3
"""
Cross-platform installer for Claude Code hooks.

Works on Mac, Linux, and Windows.

Usage:
    python .claude/hooks/install.py
    python3 .claude/hooks/install.py
"""

import json
import os
import platform
import shutil
import stat
import sys
from pathlib import Path


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.resolve()


def get_claude_dir():
    """Get the .claude directory."""
    return get_project_root() / ".claude"


def get_hooks_dir():
    """Get the hooks directory."""
    return get_claude_dir() / "hooks"


def is_windows():
    """Check if running on Windows."""
    return platform.system() == "Windows"


def make_executable(path):
    """Make a file executable (Unix only)."""
    if not is_windows():
        current = os.stat(path).st_mode
        os.chmod(path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_settings():
    """Install Claude Code settings from template."""
    template = get_claude_dir() / "settings.template.json"
    target = get_claude_dir() / "settings.local.json"

    if not template.exists():
        print(f"ERROR: Template not found: {template}")
        return False

    if target.exists():
        print(f"Settings already exist: {target}")
        response = input("Overwrite? [y/N]: ").strip().lower()
        if response != "y":
            print("Skipping settings installation.")
            return True

    # Read template
    with open(template, "r") as f:
        settings = json.load(f)

    # Update hook command based on platform
    # Use Python for cross-platform compatibility
    python_cmd = "python3" if not is_windows() else "python"
    hook_cmd = f"{python_cmd} \"$CLAUDE_PROJECT_DIR/.claude/hooks/code-review.py\""

    # Update the hook command in settings
    if "hooks" in settings and "PostToolUse" in settings["hooks"]:
        for hook_config in settings["hooks"]["PostToolUse"]:
            if "hooks" in hook_config:
                for hook in hook_config["hooks"]:
                    if "code-review" in hook.get("command", ""):
                        hook["command"] = hook_cmd

    # Write settings
    with open(target, "w") as f:
        json.dump(settings, f, indent=2)

    print(f"Installed: {target}")
    return True


def install_git_hooks():
    """Install git pre-commit hook."""
    project_root = get_project_root()
    git_hooks_dir = project_root / ".git" / "hooks"
    source_hooks_dir = project_root / "hooks"

    if not git_hooks_dir.exists():
        print("WARNING: .git/hooks not found - skipping git hooks")
        return True

    if not source_hooks_dir.exists():
        print("WARNING: hooks/ directory not found - skipping git hooks")
        return True

    # Install pre-commit hook
    pre_commit_src = source_hooks_dir / "pre-commit"
    pre_commit_dst = git_hooks_dir / "pre-commit"

    if pre_commit_src.exists():
        shutil.copy2(pre_commit_src, pre_commit_dst)
        make_executable(pre_commit_dst)
        print(f"Installed git hook: {pre_commit_dst}")

    return True


def verify_python():
    """Verify Python is available."""
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    return True


def print_instructions():
    """Print post-install instructions."""
    print()
    print("=" * 50)
    print("  Installation Complete!")
    print("=" * 50)
    print()
    print("Claude Code hooks are now active.")
    print()
    print("What happens now:")
    print("  - After every Write/Edit, code is automatically reviewed")
    print("  - Security issues block the operation")
    print("  - Style warnings are shown but don't block")
    print()
    print("To test:")
    print("  1. Start Claude Code in this project")
    print("  2. Ask Claude to write/edit a file")
    print("  3. Watch for code review output")
    print()
    print("To disable temporarily:")
    print("  - Remove/rename .claude/settings.local.json")
    print()


def main():
    print()
    print("=" * 50)
    print("  Claude Code Hooks Installer")
    print("=" * 50)
    print()

    # Verify environment
    if not verify_python():
        sys.exit(1)

    print()

    # Install Claude settings
    print("Installing Claude Code settings...")
    if not install_settings():
        print("WARNING: Could not install settings")

    print()

    # Install git hooks
    print("Installing git hooks...")
    if not install_git_hooks():
        print("WARNING: Could not install git hooks")

    # Make hook scripts executable
    hooks_dir = get_hooks_dir()
    for hook_file in hooks_dir.glob("*.sh"):
        make_executable(hook_file)
        print(f"Made executable: {hook_file.name}")

    for hook_file in hooks_dir.glob("*.py"):
        make_executable(hook_file)

    print_instructions()


if __name__ == "__main__":
    main()
