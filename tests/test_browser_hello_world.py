"""
Browser E2E test: User creates animated hello world via the UI.

Uses Playwright to simulate a real user:
1. Opening the app in a browser
2. Creating a new project
3. Creating a task to build an animated hello world HTML file
4. Triggering the agent
5. Verifying the task status updates

Features:
- Takes screenshots on failure and at key steps
- Captures browser console logs for debugging
- Checks for JavaScript errors

Run with:
    cd /mnt/c/dropbox/_coding/agentic/v2
    source ../.env && pytest tests/test_browser_hello_world.py -v
    pytest tests/test_browser_hello_world.py -v --headed  # Watch in browser

Requires: pip install pytest-playwright && playwright install chromium
"""
import os
import shutil
import tempfile
import subprocess
import sys
import time
import pytest
from pathlib import Path
from playwright.sync_api import Page, expect


# Test configuration
APP_URL = "http://localhost:8002"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="module")
def test_workspace():
    """Create a temporary workspace directory for testing."""
    workspace = tempfile.mkdtemp(prefix="agentic_browser_test_")
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture(scope="module")
def app_server(test_workspace):
    """Start the FastAPI server for testing."""
    v2_dir = Path(__file__).parent.parent

    # Load environment from .env file
    env = os.environ.copy()
    env_file = v2_dir.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"],
        cwd=str(v2_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(3)

    if server.poll() is not None:
        stdout, stderr = server.communicate()
        raise RuntimeError(f"Server failed to start:\n{stderr.decode()}")

    yield server

    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()


@pytest.fixture(autouse=True)
def setup_screenshots():
    """Ensure screenshot directory exists."""
    SCREENSHOT_DIR.mkdir(exist_ok=True)


class ConsoleLogs:
    """Capture and analyze browser console logs."""

    def __init__(self):
        self.logs = []
        self.errors = []

    def handle(self, msg):
        self.logs.append({"type": msg.type, "text": msg.text})
        if msg.type in ("error", "warning"):
            self.errors.append(msg.text)

    def has_errors(self):
        return len(self.errors) > 0

    def get_errors(self):
        return self.errors


@pytest.fixture
def console_logs(page: Page):
    """Capture console logs from the browser."""
    logs = ConsoleLogs()
    page.on("console", logs.handle)
    yield logs


def take_screenshot(page: Page, name: str):
    """Take a screenshot with the given name."""
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"Screenshot saved: {path}")
    return path


class TestBrowserHelloWorld:
    """End-to-end browser tests for creating animated hello world."""

    def test_01_page_loads(self, app_server, page: Page, console_logs):
        """User opens the app and sees the UI."""
        page.goto(APP_URL)

        # Take screenshot of initial load
        take_screenshot(page, "01_initial_load")

        # Should see the header
        expect(page.locator("h1")).to_contain_text("Agentic v2")

        # Should see Projects section
        expect(page.locator("text=Projects")).to_be_visible()

        # Should see New Project button
        expect(page.locator("text=New Project")).to_be_visible()

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_02_create_project(self, app_server, page: Page, test_workspace, console_logs):
        """User creates a new project via the dialog."""
        page.goto(APP_URL)

        # Click "New Project" button
        page.click("text=New Project")

        # Dialog should appear
        expect(page.locator(".dialog")).to_be_visible()
        take_screenshot(page, "02_project_dialog_open")

        # Fill in the form
        page.fill("#project-name", "Hello World Animation")
        page.fill("#project-path", test_workspace)
        page.select_option("#project-env", "local")

        take_screenshot(page, "02_project_form_filled")

        # Submit the form
        page.click(".dialog button[type='submit']")

        # Wait for dialog to close
        page.wait_for_selector(".dialog-overlay:not(.active)", timeout=5000)

        # Project should appear in the list
        expect(page.locator(".project-item")).to_contain_text("Hello World Animation")
        expect(page.locator(".badge-local")).to_be_visible()

        take_screenshot(page, "02_project_created")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_03_select_project(self, app_server, page: Page, console_logs):
        """User clicks on a project to select it."""
        page.goto(APP_URL)

        # Wait for projects to load
        page.wait_for_selector(".project-item", timeout=5000)

        # Click on the project
        page.click(".project-item:has-text('Hello World Animation')")

        # Project should be marked as active
        expect(page.locator(".project-item.active")).to_be_visible()

        # New Task button should appear
        expect(page.locator("#new-task-btn")).to_be_visible()

        # Tasks header should update
        expect(page.locator("#tasks-header")).to_contain_text("Tasks")

        take_screenshot(page, "03_project_selected")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_04_create_task(self, app_server, page: Page, console_logs):
        """User creates a task to build animated hello world."""
        page.goto(APP_URL)

        # Select the project first
        page.wait_for_selector(".project-item", timeout=5000)
        page.click(".project-item:has-text('Hello World Animation')")
        page.wait_for_selector("#new-task-btn", timeout=5000)

        # Click New Task button
        page.click("#new-task-btn")

        # Dialog should appear
        expect(page.locator("#task-dialog")).to_have_class(r".*active.*")
        take_screenshot(page, "04_task_dialog_open")

        # Fill in the task details
        page.fill("#task-title", "Create animated Hello World page")
        page.fill("#task-description", """Create an index.html file with:
1. A centered "Hello World" heading
2. CSS animation that makes the text fade in and pulse
3. Gradient text effect with nice colors
4. Dark background, modern styling
Use pure CSS animations.""")

        take_screenshot(page, "04_task_form_filled")

        # Submit
        page.click("#task-dialog button[type='submit']")

        # Wait for dialog to close
        page.wait_for_timeout(500)

        # Task should appear in the list
        expect(page.locator(".task-item")).to_contain_text("Create animated Hello World page")
        expect(page.locator(".badge-backlog")).to_be_visible()
        expect(page.locator(".badge-dev")).to_be_visible()

        take_screenshot(page, "04_task_created")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_05_trigger_agent(self, app_server, page: Page, console_logs):
        """User triggers the agent to work on the task."""
        page.goto(APP_URL)

        # Select project
        page.wait_for_selector(".project-item", timeout=5000)
        page.click(".project-item:has-text('Hello World Animation')")

        # Wait for tasks to load
        page.wait_for_selector(".task-item", timeout=5000)

        take_screenshot(page, "05_before_trigger")

        # Handle the alert that will appear
        page.on("dialog", lambda dialog: dialog.accept())

        # Click the Run button
        page.click(".task-item .btn-success")

        # Wait for the request
        page.wait_for_timeout(1000)

        # Task status should change to in_progress
        expect(page.locator(".badge-in_progress")).to_be_visible()

        take_screenshot(page, "05_after_trigger")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_06_verify_task_details_visible(self, app_server, page: Page, console_logs):
        """Verify task details are displayed correctly."""
        page.goto(APP_URL)

        # Select project
        page.wait_for_selector(".project-item", timeout=5000)
        page.click(".project-item:has-text('Hello World Animation')")

        # Wait for tasks
        page.wait_for_selector(".task-item", timeout=5000)

        # Should see our task
        task = page.locator(".task-item:has-text('Create animated Hello World page')")
        expect(task).to_be_visible()

        # Verify task description is displayed
        expect(task.locator(".task-description")).to_be_visible()

        # Verify status badges are shown
        expect(task.locator(".task-meta")).to_be_visible()

        take_screenshot(page, "06_task_details")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"


class TestBrowserDialogs:
    """Test dialog interactions."""

    def test_project_dialog_can_be_cancelled(self, app_server, page: Page, console_logs):
        """User can cancel the new project dialog."""
        page.goto(APP_URL)

        # Open dialog
        page.click("text=New Project")
        expect(page.locator("#project-dialog")).to_have_class(r".*active.*")

        # Cancel
        page.click("#project-dialog button:has-text('Cancel')")

        # Dialog should close
        page.wait_for_timeout(300)
        expect(page.locator("#project-dialog.active")).not_to_be_visible()

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"


class TestBrowserEmptyStates:
    """Test empty states in the UI."""

    def test_empty_tasks_message(self, app_server, page: Page, console_logs):
        """Empty state is shown when no project selected."""
        page.goto(APP_URL)

        # Should see empty state message
        expect(page.locator("#tasks-list .empty")).to_be_visible()
        expect(page.locator("#tasks-list .empty")).to_contain_text("Select a project")

        take_screenshot(page, "empty_state")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"


# Pytest hook to take screenshot on failure
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Take screenshot on test failure."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        # Get the page fixture if available
        try:
            page = item.funcargs.get("page")
            if page:
                test_name = item.name.replace("[", "_").replace("]", "_")
                take_screenshot(page, f"FAILED_{test_name}")
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
