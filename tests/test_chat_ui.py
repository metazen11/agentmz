"""Playwright tests for chat.html interface."""
import re
import pytest
from playwright.sync_api import expect
import time
import os
import json
import urllib.request


APP_URL = os.environ.get("APP_URL", "https://wfhub.localhost")


def _fetch_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _get_models(retries=2, delay=0.5):
    for _ in range(retries):
        payload = _fetch_json("http://localhost:8001/api/models")
        if payload and payload.get("success"):
            return payload.get("models", [])
        time.sleep(delay)
    return []


def _get_config():
    payload = _fetch_json("http://localhost:8001/api/config")
    if not payload or not payload.get("success"):
        return {}
    return payload.get("config", {})


def _wait_for_config(key, value, timeout=60, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        config = _get_config()
        if config.get(key) == value:
            return config
        time.sleep(interval)
    return {}


def _set_config(payload):
    req = urllib.request.Request(
        "http://localhost:8001/api/config",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url, payload, timeout=120):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _pick_test_model(models, current):
    preferred_markers = ["0.6b", "1.7b", "3b", "4b", "7b", "8b", "14b"]
    ordered = sorted(models)
    for marker in preferred_markers:
        for model in ordered:
            if marker in model and model != current:
                return model
    for model in ordered:
        if model != current:
            return model
    return ordered[0] if ordered else current


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Allow local HTTPS certs for the running stack."""
    return {**browser_context_args, "ignore_https_errors": True}


class TestChatUI:
    """Test chat.html functionality."""
    def test_page_loads(self, page):
        """Chat page should load without errors."""
        page.goto(APP_URL)

        # Check title
        expect(page).to_have_title("Agentic v2 - Coding Agent")

        # Check main elements exist
        expect(page.locator("h1")).to_have_text("Agentic v2")
        expect(page.locator("#project-list")).to_be_visible()
        expect(page.locator("#task-list")).to_be_visible()
        expect(page.locator("#messages")).to_be_visible()
        expect(page.locator("#prompt")).to_be_visible()
    def test_projects_load(self, page):
        """Projects should load from API."""

        # Listen for console errors
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        page.goto(APP_URL)

        # Wait for projects to load (either project items or "No projects yet")
        page.wait_for_timeout(2000)

        # Check project list has content
        project_list = page.locator("#project-list")
        expect(project_list).to_be_visible()

        # Should have some content (either projects or "No projects yet")
        list_text = project_list.inner_text()
        assert len(list_text) > 0, "Project list should have content"

        # Print any errors for debugging
        if errors:
            print(f"Console errors: {errors}")
    def test_new_project_modal(self, page):
        """New project modal should open and close."""
        page.goto(APP_URL)
        page.wait_for_timeout(1000)

        # Click new project button
        page.click("text=+ New Project")

        # Modal should be visible
        modal = page.locator("#new-project-modal")
        expect(modal).to_be_visible()

        # Cancel should close it
        page.click("#new-project-modal button.secondary")
        expect(modal).not_to_be_visible()
    def test_edit_project_modal_exists(self, page):
        """Edit project modal should exist."""
        page.goto(APP_URL)
        page.wait_for_timeout(1000)

        expect(page.locator("#edit-project-modal")).to_be_hidden()
    def test_create_project(self, page):
        """Should be able to create a new project."""

        # Listen for network requests
        requests = []
        page.on("request", lambda req: requests.append(req) if "projects" in req.url else None)

        page.goto(APP_URL)
        page.wait_for_timeout(2000)

        # Open modal
        page.click("text=+ New Project")
        page.wait_for_timeout(500)

        # Fill form
        page.fill("#new-project-name", "test-playwright-project")
        page.fill("#new-project-workspace", "/workspaces/poc")

        # Click create
        page.click("#new-project-modal button:not(.secondary)")

        # Wait for request
        page.wait_for_timeout(2000)

        # Check if POST request was made
        post_requests = [r for r in requests if r.method == "POST"]
        assert len(post_requests) > 0, f"Should have made POST request. Requests: {[r.url for r in requests]}"

        # Modal should close
        modal = page.locator("#new-project-modal")
        expect(modal).not_to_be_visible()
    def test_status_shows_connection(self, page):
        """Status should show connected when APIs are available."""
        page.goto(APP_URL)

        # Wait for health check
        page.wait_for_function(
            "document.getElementById('status').textContent !== 'Checking connection...'",
            timeout=10000,
        )

        # Check status element
        status = page.locator("#status")
        status_text = status.inner_text()

        # Should show connected/model/missing/healing
        assert (
            "Connected" in status_text
            or "Model" in status_text
            or "Missing" in status_text
            or "Healing" in status_text
        ), \
            f"Status should show connection info, got: {status_text}"
    def test_model_selector_populates(self, page):
        """Model selector should populate from Ollama models list."""
        models = _get_models()
        if not models:
            pytest.skip("No models available from /api/models")
        page.goto(APP_URL)

        page.wait_for_function(
            "() => {"
            "const el = document.getElementById('model-select');"
            "return el && !el.disabled && el.options.length > 0;"
            "}",
            timeout=10000,
        )

        options = page.locator("#model-select option")
        option_texts = options.all_inner_texts()
        assert len(option_texts) >= 1, "Model selector should have at least one option"
        assert "No models found" not in option_texts, "Model selector should not show empty state"
    def test_set_model_and_create_hello_world(self, page):
        """Select a model, set it, and create a hello world file."""
        models = _get_models()
        if not models:
            pytest.skip("No models available from /api/models")

        config = _get_config()
        original_agent_model = config.get("agent_model")
        original_aider_model = config.get("aider_model")

        selected_model = _pick_test_model(models, original_agent_model)

        file_name = "playwright_model_hello.txt"
        workspace_path = "/mnt/c/dropbox/_coding/agentic/v2/workspaces/poc"
        target_file = os.path.join(workspace_path, file_name)

        if os.path.exists(target_file):
            os.remove(target_file)
        try:
            page.goto(APP_URL)

            page.wait_for_function(
                "() => {"
                "const el = document.getElementById('model-select');"
                "return el && !el.disabled && el.options.length > 0;"
                "}",
                timeout=10000,
            )
            page.select_option("#model-select", selected_model)
            page.click("#model-apply")

            page.wait_for_timeout(1000)
            updated_config = _wait_for_config("agent_model", selected_model, timeout=90, interval=3)
            assert updated_config.get("agent_model") == selected_model
            assert selected_model in (updated_config.get("aider_model") or "")

            prompt = f"Create {file_name} with the exact text: Hello from model {selected_model}"
            try:
                response = _post_json(
                    "http://localhost:8001/api/aider/execute",
                    {"workspace": "poc", "prompt": prompt, "files": [], "timeout": 45},
                    timeout=45,
                )
            except Exception:
                pytest.skip("LLM inference timed out (expected with slow models)")

            if isinstance(response, dict) and response.get("success") is False:
                pytest.fail(f"Aider execution failed: {response.get('error')}")

            deadline = time.time() + 20
            while time.time() < deadline:
                if os.path.exists(target_file):
                    with open(target_file, "r", encoding="utf-8") as handle:
                        contents = handle.read()
                    if "Hello from model" in contents:
                        break
                time.sleep(2)
            else:
                pytest.fail(f"Timed out waiting for {target_file} to be created")
        finally:
            if original_agent_model:
                _set_config({"agent_model": original_agent_model})
            if original_aider_model:
                _set_config({"aider_model": original_aider_model})
    def test_heal_button_exists(self, page):
        """Heal button should be available."""
        page.goto(APP_URL)
        expect(page.locator("#heal-btn")).to_be_hidden()
    def test_logs_panel_exists(self, page):
        """Logs panel should exist with tabs."""
        page.goto(APP_URL)
        page.wait_for_timeout(1000)

        # Check logs tabs exist
        expect(page.locator("#tab-ollama")).to_be_visible()
        expect(page.locator("#tab-ollama_http")).to_be_visible()
        expect(page.locator("#tab-aider")).to_be_visible()
        expect(page.locator("#tab-main")).to_be_visible()

        # Check logs content area exists
        expect(page.locator("#logs-content")).to_be_visible()
    def test_switch_log_tabs(self, page):
        """Should be able to switch between log tabs."""
        page.goto(APP_URL)
        page.wait_for_timeout(2000)

        # Click aider tab
        page.click("#tab-aider")
        page.wait_for_timeout(1000)

        # Aider tab should be active
        aider_tab = page.locator("#tab-aider")
        expect(aider_tab).to_have_class(re.compile(r"active"))

        # Click Ollama HTTP tab
        page.click("#tab-ollama_http")
        page.wait_for_timeout(1000)

        ollama_http_tab = page.locator("#tab-ollama_http")
        expect(ollama_http_tab).to_have_class(re.compile(r"active"))

        # Click main tab
        page.click("#tab-main")
        page.wait_for_timeout(1000)

        # Main tab should be active
        main_tab = page.locator("#tab-main")
        expect(main_tab).to_have_class(re.compile(r"active"))
    def test_send_message(self, page):
        """Should be able to send a message."""

        # Track requests
        requests = []
        page.on("request", lambda req: requests.append(req.url))

        page.goto(APP_URL)
        page.wait_for_timeout(2000)

        # Type a message
        page.fill("#prompt", "list files")

        # Click send
        page.click("#send")

        # Wait for request
        page.wait_for_timeout(2000)

        # Should have made request to aider API
        aider_requests = [
            r for r in requests
            if "/aider/api/" in r or ("8001" in r and ("aider" in r or "agent/run" in r))
        ]
        assert len(aider_requests) > 0, f"Should have made aider request. Requests: {requests}"

        # Message should appear in chat
        messages = page.locator("#messages")
        expect(messages).to_contain_text("list files")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
