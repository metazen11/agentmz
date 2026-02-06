import os
import re
import pytest
import json
import urllib.request
import time
import ssl # NEW: Import ssl
from playwright.sync_api import expect, Page

APP_URL = os.environ.get("APP_URL", "http://localhost:8080/chat.html")
AIDER_API_URL = os.environ.get("AIDER_API_URL", "http://localhost:8001/")

# NEW: Create an unverified SSL context for local HTTPS
try:
    _unverified_https_context = ssl._create_unverified_context()
except AttributeError:
    # Fallback for older Python versions or environments without _create_unverified_context
    _unverified_https_context = None

# Helper function to post JSON to an API endpoint
def _post_json(url, payload, timeout=60):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Pass the unverified context to urlopen
    with urllib.request.urlopen(req, timeout=timeout, context=_unverified_https_context) as response:
        return json.loads(response.read().decode("utf-8"))

# Helper function to get config from Aider API
def _get_aider_config(retries=5, delay=1):
    for _ in range(retries):
        try:
            # Pass the unverified context to urlopen
            with urllib.request.urlopen(f"{AIDER_API_URL}/api/config", timeout=5, context=_unverified_https_context) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("success"):
                    return data.get("config")
        except Exception:
            pass
        time.sleep(delay)
    return None

# Helper function to set config on Aider API
def _set_aider_config(payload):
    return _post_json(f"{AIDER_API_URL}/api/config", payload)

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Allow local HTTPS certs for the running stack."""
    return {**browser_context_args, "ignore_https_errors": True}

@pytest.fixture(autouse=True)
def setup_default_project(page: Page):
    """Ensure a default project (poc) is selected and Aider workspace is set by UI interaction."""
    page.goto(APP_URL)
    expect(page.locator("h1")).to_have_text("Agentic v2")

    # Wait for window.state to be initialized and projects loaded
    page.wait_for_function(
        "() => window.state && Array.isArray(window.state.projects) && window.state.projects.length > 0",
        timeout=15000 # Increased timeout
    )
    # Now, wait for selectedProject to be set by the UI's init() or restoreSelectionsFromCookies()
    page.wait_for_function(
        "() => window.state.selectedProject !== undefined && window.state.selectedProject !== null",
        timeout=15000
    )


    # Check if 'poc' is already selected in the UI
    current_selected_project_name = page.evaluate("() => window.state.selectedProject?.name")
    
    if current_selected_project_name != "poc":
        print("Selecting 'poc' project in UI.")
        # Find the project ID for 'poc'
        poc_project_id = page.evaluate("() => window.state.projects.find(p => p.name === 'poc')?.id")
        if poc_project_id:
            page.locator(f".project-list li[onclick*='selectProject({poc_project_id})']").click()
            
            # Wait for the UI to confirm 'poc' is selected
            page.wait_for_function(
                "() => window.state.selectedProject?.name === 'poc'",
                timeout=10000
            )
            # Also wait for the Aider API config to confirm the switch (optional, but good for robustness)
            page.wait_for_function(
                f"() => {{ const config = window.state.aiderConfig; return config && config.current_workspace === 'poc'; }}",
                timeout=10000
            )
            print("Confirmed 'poc' project selected via UI interaction.")
        else:
            pytest.fail("Project 'poc' not found in the UI. Ensure it exists or is created by the setup.")
    else:
        print("Project 'poc' already selected in UI.")

    # Ensure status is connected
    expect(page.locator("#status")).to_contain_text(re.compile(r"(Connected|Model:)"))

class TestDirectChatInteraction:
    def test_send_hello_and_get_response(self, page: Page):
        """
        Tests sending a simple 'say hello' message and asserting a response.
        This verifies the frontend chat interaction with the Aider API in chat_mode.
        """
        page.goto(APP_URL) # Ensure we are on the chat page

        # Type "say hello" into the prompt
        prompt_textarea = page.locator("#prompt")
        expect(prompt_textarea).to_be_visible()
        prompt_textarea.fill("say hello")

        # Click the send button
        send_button = page.locator("#send")
        expect(send_button).to_be_enabled()
        send_button.click()

        # Wait for an assistant message to appear
        assistant_message = page.locator(".message.assistant").last
        expect(assistant_message).to_be_visible(timeout=60000) # Increased timeout for LLM response

        # Assert the assistant's response contains a greeting
        # The exact response might vary, so check for common greeting words or an indication of response
        response_text = assistant_message.text_content()
        print(f"Agent response: {response_text}")
        assert "hello" in response_text.lower() or \
               "hi there" in response_text.lower() or \
               "greetings" in response_text.lower() or \
               "how can I help" in response_text.lower() or \
               "i am a coding assistant" in response_text.lower() or \
               "i am aider" in response_text.lower() or \
               "as a coding agent" in response_text.lower()
        
        # Optionally, check that the status returns to 'Ready' or 'Connected'
        expect(page.locator("#status")).to_contain_text(re.compile(r"(Ready|Connected)"))

    def test_send_complex_query_and_get_response(self, page: Page):
        """
        Tests sending a more complex query to verify full interaction capabilities.
        """
        page.goto(APP_URL)

        prompt_textarea = page.locator("#prompt")
        expect(prompt_textarea).to_be_visible()
        prompt_textarea.fill("what files are in the current workspace?")

        send_button = page.locator("#send")
        expect(send_button).to_be_enabled()
        send_button.click()

        assistant_message = page.locator(".message.assistant").last
        expect(assistant_message).to_be_visible(timeout=60000)

        response_text = assistant_message.text_content()
        print(f"Agent response: {response_text}")
        
        # Expect the agent to list files or indicate it can use tools to do so
        assert ("files" in response_text.lower() or 
                "current directory" in response_text.lower() or
                "workspace" in response_text.lower() or
                "use the `glob` tool" in response_text.lower() or
                "i can use my tools to find files" in response_text.lower())
        
        expect(page.locator("#status")).to_contain_text(re.compile(r"(Ready|Connected)"))
