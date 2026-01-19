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
    APP_URL=https://wfhub.localhost pytest tests/test_browser_hello_world.py -v
    pytest tests/test_browser_hello_world.py -v --headed  # Watch in browser

Requires: pip install pytest-playwright && playwright install chromium
"""
import os
import uuid
import pytest
from pathlib import Path
from playwright.sync_api import Page, expect


# Test configuration
APP_URL = os.environ.get("APP_URL", "https://wfhub.localhost")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="session")
def app_url():
    """Return the app URL for the running stack."""
    return APP_URL


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Allow local HTTPS certs for the running stack."""
    return {**browser_context_args, "ignore_https_errors": True}


@pytest.fixture(scope="module")
def project_name():
    """Unique project name to avoid collisions with existing data."""
    return f"Playwright {uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def workspace_name():
    """Use an existing workspace to keep tests lightweight."""
    return os.environ.get("TEST_WORKSPACE", "poc")


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
        if msg.type == "error":
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


@pytest.fixture(autouse=True)
def stub_git_status(page: Page):
    """Stub git status calls to avoid failures when git isn't available."""
    page.route(
        "**/git/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"branches": [], "remotes": [], "current": null}'
        )
    )
    yield


def take_screenshot(page: Page, name: str):
    """Take a screenshot with the given name."""
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"Screenshot saved: {path}")
    return path


class TestBrowserHelloWorld:
    """End-to-end browser tests for creating animated hello world."""

    def test_01_page_loads(self, app_url, page: Page, console_logs):
        """User opens the app and sees the UI."""
        page.goto(app_url)

        # Take screenshot of initial load
        take_screenshot(page, "01_initial_load")

        # Should see the header
        expect(page.locator("h1")).to_contain_text("Agentic v2")

        # Should see Projects section
        expect(page.get_by_role("heading", name="Projects")).to_be_visible()

        # Should see New Project button
        expect(page.get_by_role("button", name="+ New Project")).to_be_visible()

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_02_create_project(self, app_url, page: Page, project_name, workspace_name, console_logs):
        """User creates a new project via the dialog."""
        page.goto(app_url)

        # Click "New Project" button
        page.get_by_role("button", name="+ New Project").click()

        # Dialog should appear
        expect(page.locator("#new-project-modal")).to_be_visible()
        take_screenshot(page, "02_project_dialog_open")

        # Fill in the form
        page.fill("#new-project-name", project_name)
        page.fill("#new-project-workspace", workspace_name)

        take_screenshot(page, "02_project_form_filled")

        # Submit the form
        page.locator("#new-project-modal button:has-text('Create')").click()

        # Wait for dialog to close
        expect(page.locator("#new-project-modal")).to_be_hidden()

        # Project should appear in the list
        expect(page.locator("#project-list")).to_contain_text(project_name)

        take_screenshot(page, "02_project_created")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_03_select_project(self, app_url, page: Page, project_name, console_logs):
        """User clicks on a project to select it."""
        page.goto(app_url)

        # Wait for projects to load
        page.wait_for_selector("#project-list li", timeout=5000)

        # Click on the project
        page.locator("#project-list li", has_text=project_name).click()

        # Project should be marked as active
        expect(page.locator("#project-list li.selected")).to_contain_text(project_name)

        take_screenshot(page, "03_project_selected")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_04_create_task(self, app_url, page: Page, project_name, console_logs):
        """User creates a task to build animated hello world."""
        page.goto(app_url)

        # Select the project first
        page.wait_for_selector("#project-list li", timeout=5000)
        page.locator("#project-list li", has_text=project_name).click()

        # Click New Task button
        page.get_by_role("button", name="+ New Task").click()

        # Dialog should appear
        expect(page.locator("#new-task-modal")).to_be_visible()
        take_screenshot(page, "04_task_dialog_open")

        # Fill in the task details
        page.fill("#new-task-title", "Create animated Hello World page")
        page.fill("#new-task-desc", """Create an index.html file with:
1. A centered "Hello World" heading
2. CSS animation that makes the text fade in and pulse
3. Gradient text effect with nice colors
4. Dark background, modern styling
Use pure CSS animations.""")

        take_screenshot(page, "04_task_form_filled")

        # Submit
        page.locator("#new-task-modal button:has-text('Create')").click()

        # Wait for dialog to close
        expect(page.locator("#new-task-modal")).to_be_hidden()

        # Task should appear in the list
        task_item = page.locator("#task-list li", has_text="Create animated Hello World page")
        expect(task_item).to_be_visible()
        expect(task_item.locator(".task-stage.dev")).to_be_visible()
        expect(task_item.locator(".task-status.backlog")).to_be_visible()

        take_screenshot(page, "04_task_created")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_05_trigger_agent(self, app_url, page: Page, project_name, console_logs):
        """User triggers the agent to work on the task."""
        page.goto(app_url)

        # Select project
        page.wait_for_selector("#project-list li", timeout=5000)
        page.locator("#project-list li", has_text=project_name).click()

        # Wait for tasks to load
        page.wait_for_selector("#task-list li", timeout=5000)

        take_screenshot(page, "05_before_trigger")

        # Stub agent run for predictable UI test
        page.route(
            "**/aider/api/agent/run",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"success": true, "summary": "Stubbed response"}'
            )
        )

        # Select task so context is attached
        page.locator("#task-list li", has_text="Create animated Hello World page").click()
        page.locator("#edit-task-modal button:has-text('Cancel')").click()

        # Send a prompt
        page.fill("#prompt", "Create a simple hello world page.")
        page.click("#send")

        # User message should appear
        expect(page.locator(".message.user")).to_contain_text("Create a simple hello world page.")
        expect(page.locator(".message.assistant")).to_contain_text("Stubbed response")

        take_screenshot(page, "05_after_trigger")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"

    def test_06_verify_task_details_visible(self, app_url, page: Page, project_name, console_logs):
        """Verify task details are displayed correctly."""
        page.goto(app_url)

        # Select project
        page.wait_for_selector("#project-list li", timeout=5000)
        page.locator("#project-list li", has_text=project_name).click()

        # Wait for tasks
        page.wait_for_selector("#task-list li", timeout=5000)

        # Should see our task
        task = page.locator("#task-list li", has_text="Create animated Hello World page")
        expect(task).to_be_visible()

        # Open edit modal to verify task details
        task.click()
        expect(page.locator("#edit-task-modal")).to_be_visible()
        expect(page.locator("#edit-task-title")).to_have_value("Create animated Hello World page")
        page.locator("#edit-task-modal button:has-text('Cancel')").click()

        take_screenshot(page, "06_task_details")

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"


class TestBrowserDialogs:
    """Test dialog interactions."""

    def test_project_dialog_can_be_cancelled(self, app_url, page: Page, console_logs):
        """User can cancel the new project dialog."""
        page.goto(app_url)

        # Open dialog
        page.get_by_role("button", name="+ New Project").click()
        expect(page.locator("#new-project-modal")).to_be_visible()

        # Cancel
        page.locator("#new-project-modal button:has-text('Cancel')").click()

        # Dialog should close
        expect(page.locator("#new-project-modal")).to_be_hidden()

        # Check for console errors
        assert not console_logs.has_errors(), f"Console errors: {console_logs.get_errors()}"


class TestBrowserEmptyStates:
    """Test empty states in the UI."""

    def test_empty_tasks_message(self, app_url, page: Page, console_logs):
        """Empty state is shown when no project selected."""
        page.goto(app_url)

        # Should see empty state message
        expect(page.locator("#task-list")).to_contain_text("Select a project")

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
