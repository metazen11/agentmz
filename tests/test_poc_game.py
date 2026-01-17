"""POC test: Create a simple HTML/CSS game using all aider-api tools.

This test exercises each tool endpoint and creates a memory matching game.

Run with: pytest v2/tests/test_poc_game.py -v -s
Requires:
  - aider-api running on localhost:8001
  - Ollama running on localhost:11434 with qwen2.5-coder:3b model
"""

import json
import os
import pytest
import urllib.request
import urllib.error

API_URL = os.environ.get("AIDER_API_URL", "http://localhost:8001")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11435")  # v2's Ollama
WORKSPACE = "poc"


def api_get(path: str) -> dict:
    """Make a GET request to the API."""
    url = f"{API_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(path: str, data: dict, timeout: int = 60) -> dict:
    """Make a POST request to the API."""
    url = f"{API_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def ollama_available() -> bool:
    """Check if Ollama is running and has the required model."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            return any("qwen" in m for m in models)
    except Exception:
        return False


class TestPrerequisites:
    """Verify prerequisites before running game tests."""

    def test_00_aider_api_running(self):
        """Verify aider-api is running."""
        result = api_get("/health")
        assert result["status"] == "ok"
        print(f"\n  Aider API: OK")
        print(f"  Workspace: {result['current_workspace']}")
        print(f"  Model: {result['aider_model']}")

    def test_00_ollama_running(self):
        """Verify Ollama is running with required model."""
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                has_model = any("qwen" in m.lower() for m in models)
                assert has_model, f"No qwen model found. Available: {models}"
                print(f"\n  Ollama: OK")
                print(f"  Models: {', '.join(models[:3])}")
        except urllib.error.URLError:
            pytest.fail("Ollama not running at localhost:11434. Run: docker compose -f ../docker/docker-compose.yml up -d ollama")


class TestToolsWithGame:
    """Test each tool by building a simple memory game."""

    def test_01_switch_to_poc_workspace(self):
        """Switch to poc workspace."""
        result = api_post("/api/config", {"workspace": WORKSPACE})
        assert result["success"] is True
        assert result["current_workspace"] == WORKSPACE
        print(f"\n  Switched to workspace: {WORKSPACE}")

    def test_02_glob_list_files(self):
        """Test glob - list existing files in poc."""
        result = api_post("/api/glob", {"pattern": "*", "workspace": WORKSPACE})
        assert result["success"] is True
        print(f"\n  Found {result['count']} files: {result['files'][:5]}")

    def test_03_bash_create_game_dir(self):
        """Test bash - create game directory."""
        result = api_post("/api/bash", {
            "command": "mkdir -p game && echo 'Directory ready'",
            "workspace": WORKSPACE
        })
        assert result["success"] is True
        print(f"\n  Bash output: {result['stdout'].strip()}")

    def test_04_bash_verify_dir(self):
        """Verify game directory exists."""
        result = api_post("/api/bash", {
            "command": "ls -la | grep game",
            "workspace": WORKSPACE
        })
        assert result["success"] is True
        print(f"\n  Directory created: {result['stdout'].strip()}")

    def test_05_aider_create_html(self):
        """Test aider - create the game HTML file."""
        if not ollama_available():
            pytest.skip("Ollama not available")

        result = api_post("/api/aider/execute", {
            "prompt": """Create game/index.html with a simple memory matching game:
- 4x4 grid of cards (8 pairs of emoji symbols)
- Cards flip on click to reveal symbols
- Match pairs to win
- Include inline CSS and JS in the single HTML file
- Add a "Moves" counter
- Simple and working""",
            "workspace": WORKSPACE,
            "files": ["game/index.html"]
        }, timeout=180)

        print(f"\n  Aider result: success={result.get('success')}")
        if result.get("error"):
            print(f"  Error: {result['error'][:200]}")
        if result.get("output"):
            # Show last few lines of output
            lines = result["output"].strip().split("\n")
            print(f"  Output (last 5 lines):")
            for line in lines[-5:]:
                print(f"    {line[:80]}")

        assert result.get("success") is True, f"Aider failed: {result.get('error', 'unknown')}"

    def test_06_read_verify_html(self):
        """Test read - verify the HTML was created."""
        result = api_post("/api/read", {
            "path": "game/index.html",
            "workspace": WORKSPACE
        })

        if not result.get("success"):
            pytest.skip("HTML file not created (aider may have failed)")

        content = result["content"]
        assert "<html" in content.lower() or "<!doctype" in content.lower()
        print(f"\n  HTML file exists, {len(content)} chars")
        print(f"  Has game logic: {'card' in content.lower() or 'flip' in content.lower()}")

    def test_07_grep_search_game_code(self):
        """Test grep - search for game-related code."""
        result = api_post("/api/grep", {
            "pattern": "click|flip|match|card",
            "workspace": WORKSPACE,
            "path": "game"
        })
        # Grep may return 0 matches if file doesn't exist
        print(f"\n  Grep found {result.get('count', 0)} matches")
        assert result["success"] is True

    def test_08_bash_show_game_file(self):
        """Test bash - show game file info."""
        result = api_post("/api/bash", {
            "command": "ls -la game/ 2>/dev/null || echo 'game dir not found'",
            "workspace": WORKSPACE
        })
        assert result["success"] is True
        print(f"\n  Game files:\n{result['stdout']}")


class TestAgentRun:
    """Test the full agent orchestration."""

    @pytest.mark.skip(reason="Agent run takes 1-2 min. Run manually: pytest -k agent --no-skip")
    def test_agent_enhance_game(self):
        """Test agent/run - have agent enhance the game."""
        if not ollama_available():
            pytest.skip("Ollama not available")

        result = api_post("/api/agent/run", {
            "task": """Look at game/index.html and enhance it:
1. Add a nice CSS gradient background
2. Add a win celebration message when all pairs are matched
3. Make it look polished

Use the read tool first to see the current file, then use edit to make changes.""",
            "workspace": WORKSPACE
        }, timeout=300)

        print(f"\n  Agent completed: success={result.get('success')}")
        print(f"  Iterations: {result.get('iterations', 0)}")
        print(f"  Tools used: {result.get('tools_used', [])}")

        assert result.get("success") is True
