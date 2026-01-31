"""Forge configuration management."""
import os
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None

CONFIG_DIR = Path.home() / ".forge"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = {
    "defaults": {
        "model": "gemma3:4b",
        "workspace": "poc",
        "ollama_url": "http://localhost:11435",
        "max_iters": 6,
        "timeout": 120,
    },
    "models": {
        "available": [],
    },
}


def load_config() -> dict:
    """Load config from ~/.forge/config.toml."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> bool:
    """Save config to ~/.forge/config.toml."""
    if tomli_w is None:
        return False
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(config, f)
        return True
    except Exception:
        return False


def get(key: str, default: Any = None) -> Any:
    """Get a config value by dot-notation key."""
    config = load_config()
    parts = key.split(".")
    value = config
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def set_value(key: str, value: Any) -> bool:
    """Set a config value by dot-notation key."""
    config = load_config()
    parts = key.split(".")

    # Navigate to parent
    target = config
    for part in parts[:-1]:
        if part not in target:
            target[part] = {}
        target = target[part]

    # Set value
    target[parts[-1]] = value
    return save_config(config)


def list_ollama_models(ollama_url: Optional[str] = None) -> list[str]:
    """Fetch available models from Ollama."""
    import json
    try:
        import urllib.request
        url = (ollama_url or get("defaults.ollama_url", "http://localhost:11435")) + "/api/tags"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return sorted([m["name"] for m in data.get("models", [])])
    except Exception:
        return []


def format_config() -> str:
    """Format config for display."""
    config = load_config()
    lines = []

    # Defaults section
    defaults = config.get("defaults", {})
    lines.append("[defaults]")
    for key, value in defaults.items():
        lines.append(f"  {key} = {value}")

    # Models section
    models = config.get("models", {})
    if models.get("available"):
        lines.append("\n[models]")
        lines.append(f"  available = {models['available']}")

    return "\n".join(lines)


def handle_config_command(args: str) -> str:
    """Handle /config command from CLI.

    Usage:
        /config               - Show all settings
        /config model         - Show current model
        /config model NAME    - Set model
        /config list-models   - List available Ollama models
        /config workspace     - Show current workspace
        /config workspace DIR - Set workspace
    """
    parts = args.strip().split(None, 1)
    if not parts:
        # Show all config
        return format_config()

    cmd = parts[0].lower()
    value = parts[1] if len(parts) > 1 else None

    if cmd == "model":
        if value:
            if set_value("defaults.model", value):
                return f"Model set to: {value}"
            return "Error: Could not save config (install tomli-w)"
        return f"Current model: {get('defaults.model', 'gemma3:4b')}"

    elif cmd == "workspace":
        if value:
            if set_value("defaults.workspace", value):
                return f"Workspace set to: {value}"
            return "Error: Could not save config"
        return f"Current workspace: {get('defaults.workspace', 'poc')}"

    elif cmd == "list-models":
        models = list_ollama_models()
        if models:
            # Update available models in config
            set_value("models.available", models)
            return "Available models:\n  " + "\n  ".join(models)
        return "No models found (is Ollama running?)"

    elif cmd == "ollama-url" or cmd == "ollama_url":
        if value:
            if set_value("defaults.ollama_url", value):
                return f"Ollama URL set to: {value}"
            return "Error: Could not save config"
        return f"Ollama URL: {get('defaults.ollama_url', 'http://localhost:11435')}"

    elif cmd == "timeout":
        if value:
            try:
                timeout = int(value)
                if set_value("defaults.timeout", timeout):
                    return f"Timeout set to: {timeout}s"
            except ValueError:
                return "Error: timeout must be an integer"
            return "Error: Could not save config"
        return f"Timeout: {get('defaults.timeout', 120)}s"

    elif cmd == "max-iters" or cmd == "max_iters":
        if value:
            try:
                iters = int(value)
                if set_value("defaults.max_iters", iters):
                    return f"Max iterations set to: {iters}"
            except ValueError:
                return "Error: max_iters must be an integer"
            return "Error: Could not save config"
        return f"Max iterations: {get('defaults.max_iters', 6)}"

    else:
        return f"Unknown config key: {cmd}\nUse: model, workspace, list-models, ollama-url, timeout, max-iters"
