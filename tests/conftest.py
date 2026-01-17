"""
Pytest configuration and shared fixtures for v2 tests.

Usage:
    # Run all tests
    pytest tests/ -v

    # Run browser tests with visible browser
    pytest tests/test_browser_hello_world.py -v --headed

    # Run specific test
    pytest tests/test_browser_hello_world.py::TestBrowserHelloWorld::test_01_page_loads -v
"""
import os
import sys
import subprocess
import tempfile
import shutil
import time
import pytest
from pathlib import Path

# Add v2 to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    """Configure pytest."""
    # Register custom markers
    config.addinivalue_line("markers", "browser: mark test as browser-based")
    config.addinivalue_line("markers", "slow: mark test as slow running")


@pytest.fixture(scope="session")
def v2_dir():
    """Return the v2 directory path."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_workspace():
    """Create a temporary workspace for the entire test session."""
    workspace = tempfile.mkdtemp(prefix="agentic_test_")
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture(scope="session")
def app_server(v2_dir, test_workspace):
    """Start the FastAPI server for the test session."""
    # Load environment variables
    env = os.environ.copy()

    # Try to load from .env file
    env_file = v2_dir.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")

    # Start server
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"],
        cwd=str(v2_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for startup
    time.sleep(2)

    # Check if running
    if server.poll() is not None:
        stdout, stderr = server.communicate()
        raise RuntimeError(f"Server failed to start:\n{stderr.decode()}")

    yield server

    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()


@pytest.fixture(scope="session")
def app_url():
    """Return the app URL."""
    return "http://localhost:8002"


# Note: pytest-playwright provides page fixture automatically
# Use --headed flag to see browser: pytest tests/ --headed
