"""Pre-hook that warns about destructive operations.

Currently prints a warning. In future, could prompt for confirmation.
"""
import sys

# Tools that modify or delete files
DESTRUCTIVE_TOOLS = {"delete_file", "run_command"}

# Dangerous shell commands
DANGEROUS_COMMANDS = {"rm", "mv", "rmdir", "del"}


def pre_tool(tool_name: str, args: dict) -> bool:
    """Warn before destructive operations.

    Returns:
        True to proceed, False to abort.
    """
    if tool_name == "delete_file":
        path = args.get("path", "unknown")
        print(f"[HOOK] Warning: Deleting file: {path}", file=sys.stderr)
        # Return True for now - future: prompt for confirmation
        return True

    if tool_name == "run_command":
        cmd = args.get("command", "")
        # Check if command starts with dangerous operation
        cmd_parts = cmd.strip().split()
        if cmd_parts and cmd_parts[0] in DANGEROUS_COMMANDS:
            print(f"[HOOK] Warning: Destructive command: {cmd}", file=sys.stderr)
            # Return True for now - future: prompt for confirmation
            return True

    return True
