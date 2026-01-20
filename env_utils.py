"""Shared environment loading utilities."""
from pathlib import Path
import os

from dotenv import load_dotenv


def load_env() -> Path:
    """Load .env from the project root if present."""
    root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent)).resolve()
    env_path = root / ".env"
    load_dotenv(env_path)
    return env_path
