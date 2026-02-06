#!/usr/bin/env python3
"""
Session Init Hook - Injects directives into Claude Code sessions.

Configurable via session-init.yml in the same directory.
"""

import os
import re
import sys
from pathlib import Path

# Try to import yaml, fall back to basic parsing if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    defaults = {
        "mode": "sections",
        "sections": [0, 5],
        "source_file": "AGENTS.md",
        "max_lines": 100,
        "prefix": "SESSION DIRECTIVES (from AGENTS.md):",
        "reminder_text": "REMINDER: Review and comply with AGENTS.md directives.",
    }

    if not config_path.exists():
        return defaults

    content = config_path.read_text()

    if HAS_YAML:
        config = yaml.safe_load(content) or {}
    else:
        # Basic YAML-like parsing for simple key: value pairs
        config = {}
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                # Handle basic types
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                elif value.startswith("[") and value.endswith("]"):
                    # Basic list parsing: [0, 5, 17]
                    value = [int(x.strip()) for x in value[1:-1].split(",") if x.strip()]
                elif value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                config[key] = value

    # Merge with defaults
    return {**defaults, **config}


def extract_sections(content: str, section_numbers: list) -> str:
    """Extract specific sections from markdown content."""
    # Pattern matches ## N. Title or ## N Title
    section_pattern = re.compile(r'^## (\d+)\.?\s+(.+)$', re.MULTILINE)

    # Find all section positions
    sections = []
    for match in section_pattern.finditer(content):
        sections.append({
            "number": int(match.group(1)),
            "title": match.group(2),
            "start": match.start(),
        })

    # Add end positions
    for i, section in enumerate(sections):
        if i + 1 < len(sections):
            section["end"] = sections[i + 1]["start"]
        else:
            section["end"] = len(content)

    # Extract requested sections
    extracted = []
    for section in sections:
        if section["number"] in section_numbers:
            text = content[section["start"]:section["end"]].strip()
            extracted.append(text)

    return "\n\n".join(extracted)


def main():
    # Determine paths
    script_dir = Path(__file__).parent
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", script_dir.parent.parent))
    config_path = script_dir / "session-init.yml"

    # Load configuration
    config = load_config(config_path)

    # Handle "off" mode
    if config["mode"] == "off":
        print("Success")
        return 0

    # Handle "reminder" mode
    if config["mode"] == "reminder":
        print(config["reminder_text"])
        return 0

    # Load source file
    source_path = project_dir / config["source_file"]
    if not source_path.exists():
        print(f"Warning: {config['source_file']} not found")
        return 0

    content = source_path.read_text()

    # Handle different modes
    if config["mode"] == "full":
        output = content
    elif config["mode"] == "sections":
        output = extract_sections(content, config["sections"])
    else:
        print(f"Unknown mode: {config['mode']}")
        return 1

    # Apply line limit
    lines = output.splitlines()
    if len(lines) > config["max_lines"]:
        lines = lines[:config["max_lines"]]
        lines.append(f"\n... (truncated at {config['max_lines']} lines)")
    output = "\n".join(lines)

    # Output with prefix
    if config["prefix"]:
        print(config["prefix"])
        print()
    print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
