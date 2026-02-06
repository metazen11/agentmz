"""Pytest configuration for Forge tests."""

# Skip problematic symlinked helper that Windows can't stat
collect_ignore = ["tests/activate_venv.sh"]
