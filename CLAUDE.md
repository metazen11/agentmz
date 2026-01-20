# Workflow Hub v2 - Agent Directives

> Canonical reference for LLM agents and developers. Read ENTIRELY before ANY work.

---

## Project Overview

**Workflow Hub v2** is a minimal agentic task orchestration system with AI-powered code editing via Aider and local LLMs via Ollama.

| Attribute | Value |
|-----------|-------|
| **Purpose** | AI coding agent with tool calling (grep, glob, bash, read, edit) |
| **Stack** | FastAPI + SQLAlchemy + PostgreSQL + Aider + Ollama |
| **Database** | PostgreSQL 16 (port 5433) |
| **Models** | qwen3:1.7b (code), qwen3:4b (general) |
| **Container Runtime** | Docker Compose |

---

## Quick Reference

```bash
# === STARTUP ===
cd /mnt/c/dropbox/_coding/agentic/v2
./start.sh                                    # Start all services

# === TESTING ===
pytest tests/ -v                              # All tests
pytest tests/test_aider_api.py -v             # API tests only
pytest tests/test_poc_game.py -v -s           # POC integration test

# === DOCKER ===
docker compose --env-file .env -f docker/docker-compose.yml up -d      # Start
docker compose --env-file .env -f docker/docker-compose.yml down       # Stop (keeps data)
docker compose --env-file .env -f docker/docker-compose.yml logs -f    # Logs
docker compose --env-file .env -f docker/docker-compose.yml build aider-api  # Rebuild

# === DATABASE ===
alembic upgrade head                          # Run migrations
alembic revision --autogenerate -m "desc"     # Create migration
alembic current                               # Check migration status
alembic history                               # Migration history
alembic stamp head                            # Mark as current (skip migrations)

# === VERIFICATION (use pytest, not curl) ===
pytest tests/test_aider_api.py::TestHealth -v  # Verify API health
pytest tests/test_aider_api.py -v              # Full API test suite
```

---

## Architecture

```
v2/
├── .env                      # ALL configuration (single source of truth)
├── start.sh                  # Startup script (validates dependencies)
├── CLAUDE.md                 # THIS FILE - agent directives
├── README.md                 # Project documentation
├── session_handoff.md        # Session state tracking
│
├── scripts/
│   └── aider_api.py          # Coding Agent HTTP API (core service)
│
├── docker/
│   ├── docker-compose.yml    # Container orchestration
│   └── Dockerfile.aider-api  # Aider API container
│
├── models.py                 # SQLAlchemy models (Project, Task)
├── database.py               # Database connection
├── alembic/                  # Database migrations
│   ├── alembic.ini
│   └── versions/
│
├── tests/
│   ├── test_aider_api.py     # API endpoint tests
│   └── test_poc_game.py      # Integration tests
│
├── workspaces/               # Project workspaces (mounted to containers)
│   └── poc/                  # Default workspace
│       ├── game/             # Test output
│       └── chat.html         # Web UI
│
└── container_manager.py      # Docker SDK for dynamic containers
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check + config |
| GET | `/api/config` | Full configuration + workspaces |
| POST | `/api/config` | Update workspace, model, iterations |
| POST | `/api/agent/run` | Execute full agent task loop |
| POST | `/api/aider/execute` | Single Aider code edit |
| POST | `/api/grep` | Search file contents (regex) |
| POST | `/api/glob` | Find files by pattern |
| POST | `/api/bash` | Run shell commands |
| POST | `/api/read` | Read file contents |

### Response Format (ALL endpoints)

```json
// Success
{"success": true, "data": {...}}

// Failure
{"success": false, "error": "Human-readable error message"}
```

---

## Canonical Naming Conventions

> **ONE correct name per concept. Use it EVERYWHERE.**

| Context | Convention | Example |
|---------|------------|---------|
| Python variables | `snake_case` | `workspace_path`, `max_iterations` |
| Python functions | `snake_case` | `run_agent()`, `get_config()` |
| Python classes | `PascalCase` | `AiderAPIHandler`, `Config` |
| Python constants | `UPPER_SNAKE_CASE` | `TOOL_DEFINITIONS`, `MAX_ITER` |
| Database tables | `snake_case`, plural | `projects`, `tasks` |
| Database columns | `snake_case` | `workspace_path`, `created_at` |
| API endpoints | `/api/noun/verb` | `/api/agent/run`, `/api/config` |
| Environment vars | `UPPER_SNAKE_CASE` | `OLLAMA_API_BASE`, `AIDER_MODEL` |
| Docker services | `kebab-case` | `wfhub-v2-db`, `aider-api` |
| File names | `snake_case.py` | `aider_api.py`, `test_aider_api.py` |
| Test functions | `test_<what>_<expected>` | `test_grep_finds_matches()` |
| CSS classes | `kebab-case` | `agent-panel`, `tool-output` |
| JavaScript | `camelCase` | `runAgent()`, `getConfig()` |

### Naming Rules

1. **Atomic** - Each name represents exactly ONE thing
2. **Canonical** - ONE correct name per concept (no synonyms)
3. **Deterministic** - Same context = same name (anyone arrives at same name)
4. **Self-documenting** - Name reveals purpose without comments

```python
# WRONG: Multiple names for same concept
ws_path, workspace, work_dir, proj_path  # Confusing synonyms

# RIGHT: One canonical name
workspace_path  # Used everywhere for workspace directory path
```

---

## Configuration

All configuration lives in `.env`. NEVER hardcode values.

```bash
# .env - Single Source of Truth
OLLAMA_API_BASE=http://localhost:11434
AIDER_MODEL=ollama_chat/qwen3:1.7b
AGENT_MODEL=qwen3:1.7b
MAX_ITERATIONS=20
DEFAULT_WORKSPACE=poc
AIDER_API_PORT=8001

# Database
DATABASE_URL=postgresql://wfhub:wfhub@localhost:5433/agentic
POSTGRES_USER=wfhub
POSTGRES_PASSWORD=wfhub
POSTGRES_DB=agentic
```

### Config Access Pattern

```python
# In code - use Config class
from scripts.aider_api import config

workspace = config.current_workspace
model = config.aider_model

# In Docker - use env_file
services:
  aider-api:
    env_file:
      - ../.env  # Never use ${VAR:-default} patterns
```

---

## Database & Migrations

### Schema (SQLAlchemy models in `models.py`)

```python
# Project - represents a codebase/workspace
class Project(Base):
    __tablename__ = "projects"
    id: int                    # Primary key
    name: str                  # Display name
    workspace_path: str        # Path under workspaces/
    environment: dict          # JSON config
    created_at: datetime

# Task - work item for agent
class Task(Base):
    __tablename__ = "tasks"
    id: int                    # Primary key
    project_id: int            # FK to projects
    parent_id: int | None      # FK to tasks (subtasks)
    title: str                 # Short description
    description: str           # Full requirements
    status: str                # backlog | in_progress | done | failed
    node_id: int               # task_nodes.id
    created_at: datetime
```

### Alembic Migrations

```bash
# Create new migration after model changes
alembic revision --autogenerate -m "Add status column to tasks"

# Apply all pending migrations
alembic upgrade head

# Check current state
alembic current

# Rollback one migration
alembic downgrade -1

# Mark database as current (skip applying)
alembic stamp head
```

### Migration Rules

1. **ALWAYS** create migration for schema changes
2. **NEVER** manually edit database schema
3. **TEST** migrations on fresh database before committing
4. **INCLUDE** both upgrade and downgrade paths

---

## Testing Standards

### CRITICAL: Use Playwright for Functional Tests, NOT curl

**curl only fetches bytes - it does NOT execute JavaScript or test real functionality.**
**Playwright runs a real browser - clicks buttons, fills forms, validates actual behavior.**

```python
# WRONG: curl/requests only tests HTTP, not actual functionality
curl http://localhost:8001/health                    # Just gets bytes
requests.get("http://localhost:8001/health")         # No JS, no browser

# RIGHT: Playwright tests real functionality
from playwright.sync_api import sync_playwright

def test_chat_sends_message():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:8080/chat.html")
        page.fill("#prompt-input", "list files")
        page.click("#send-btn")
        page.wait_for_selector(".response", timeout=30000)
        assert page.locator(".response").is_visible()
        browser.close()
```

### When to Use Each Tool

| Tool | Use For | Example |
|------|---------|---------|
| **Playwright** | UI testing, JS execution, form submission, E2E | chat.html, buttons, forms |
| **pytest + requests** | Pure JSON API endpoints (no UI) | /api/grep returns JSON |
| **NEVER curl** | Nothing in automated tests | curl is manual debug only |

### TDD Workflow (Red -> Green -> Refactor)

```bash
# 1. Write failing test
pytest tests/test_feature.py::test_new_feature -v  # Should FAIL

# 2. Implement minimum code to pass
# ... write code ...

# 3. Run test
pytest tests/test_feature.py::test_new_feature -v  # Should PASS

# 4. Refactor if needed
# 5. Run full suite
pytest tests/ -v  # All should PASS
```

### Playwright Test Pattern (UI/Browser Tests)

```python
# tests/e2e/test_chat_ui.py - ALWAYS use for browser tests
import pytest
from playwright.sync_api import sync_playwright, expect

class TestChatUI:
    """Browser tests - USE PLAYWRIGHT, NOT CURL."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page()
        yield
        self.browser.close()
        self.playwright.stop()

    def test_chat_page_loads(self):
        """Chat page loads and shows input."""
        self.page.goto("http://localhost:8080/chat.html")
        expect(self.page.locator("#prompt-input")).to_be_visible()

    def test_send_message_shows_response(self):
        """Sending message displays response."""
        self.page.goto("http://localhost:8080/chat.html")
        self.page.fill("#prompt-input", "list files")
        self.page.click("#send-btn")
        self.page.wait_for_selector(".response", timeout=30000)
        expect(self.page.locator(".response")).to_be_visible()
```

### API Test Pattern (JSON Endpoints Only)

```python
# tests/test_aider_api.py - for pure JSON API tests
import pytest
import requests

BASE_URL = "http://localhost:8001"

class TestHealth:
    """Health endpoint tests."""

    def test_health_returns_ok(self):
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

class TestGrep:
    """Grep tool tests."""

    def test_grep_finds_matches(self):
        result = requests.post(
            f"{BASE_URL}/api/grep",
            json={"pattern": "html", "workspace": "poc"}
        ).json()
        assert result["success"] is True
        assert result["count"] > 0
```

### Test Naming Convention

```python
# Pattern: test_<what>_<expected_behavior>
def test_grep_finds_matches():           # API + expected result
def test_config_returns_workspaces():    # API + expected result
def test_chat_page_loads():              # UI + state (Playwright)
def test_form_submission_creates_file(): # UI + side effect (Playwright)
```

---

## Code Patterns

### Structured Error Handling

```python
def process_request(data: dict) -> dict:
    """All functions return structured JSON."""
    try:
        result = dangerous_operation(data)
        return {"success": True, "data": result}
    except ValueError as e:
        # Expected errors - log warning, return gracefully
        logger.warning(f"Validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Unexpected errors - log error with traceback
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"success": False, "error": "Internal error"}
```

### Input Validation

```python
def _run_bash(self, data: dict) -> dict:
    """ALWAYS validate input at entry point."""
    command = data.get("command")

    # Required field check
    if not command:
        return {"success": False, "error": "command required"}

    # Type validation
    if not isinstance(command, str):
        return {"success": False, "error": "command must be string"}

    # Safety validation
    dangerous = ["rm -rf /", "dd if=", "mkfs"]
    for d in dangerous:
        if d in command.lower():
            return {"success": False, "error": f"Blocked: {d}"}

    # Proceed with validated input
    ...
```

### Path Security

```python
def _run_read(self, data: dict) -> dict:
    """ALWAYS validate paths stay within workspace."""
    file_path = os.path.join(workspace_path, path)

    # Resolve to absolute paths
    real_workspace = os.path.realpath(workspace_path)
    real_file = os.path.realpath(file_path)

    # Security check - prevent directory traversal
    if not real_file.startswith(real_workspace):
        return {"success": False, "error": "Access denied: path outside workspace"}
```

---

## Agent Directives

### MUST DO (Required for ALL work)

1. **Read before writing** - ALWAYS read existing files before modifying
2. **Tests first** - Write failing test BEFORE implementation (TDD)
3. **Validate tests pass** - Task not complete until `pytest tests/ -v` passes
4. **Use canonical names** - One name per concept, used everywhere
5. **Structured JSON responses** - `{"success": true/false, ...}`
6. **Input validation** - Validate ALL inputs server-side
7. **Path security** - Verify paths stay within workspace boundaries
8. **Environment variables** - All config in `.env`, never hardcoded
9. **Alembic for migrations** - NEVER manually edit database schema
10. **Update session_handoff.md** - Track progress and state changes
11. **Run from v2 directory** - All commands relative to `/mnt/c/dropbox/_coding/agentic/v2`
12. **Verify before presenting** - Test code works before claiming completion

### MUST NOT DO (Violations are unacceptable)

1. **Skip tests** - Task is NOT complete until tests pass
2. **Hardcode configuration** - NEVER put config values in code
3. **Duplicate services** - Reuse root Ollama (port 11434)
4. **Use Django ORM** - SQLAlchemy ONLY for all database operations
5. **Manual database changes** - ALWAYS use Alembic migrations
6. **String concatenate SQL** - Use parameterized queries only
7. **Ignore errors** - ALWAYS handle exceptions with structured responses
8. **Create synonyms** - ONE canonical name per concept
9. **Use ${VAR:-default}** - No defaults in docker-compose, use env_file
10. **Add unrequested features** - Stay focused on the task
11. **Use curl for testing** - Use Playwright for UI, pytest+requests for API
12. **Present untested code** - Verify before claiming done

---

## Session Workflow

### Session Start

```bash
# 1. Navigate to project
cd /mnt/c/dropbox/_coding/agentic/v2

# 2. Read context files
cat CLAUDE.md              # This file - directives
cat session_handoff.md     # Current state
cat README.md              # Project overview

# 3. Start services
./start.sh

# 4. Verify services (use pytest, NOT curl)
pytest tests/test_aider_api.py::TestHealth -v    # API health
pytest tests/e2e/ -v                              # UI with Playwright
```

### During Work

1. **Plan** - Break task into testable steps
2. **Test first** - Write failing test
3. **Implement** - Minimum code to pass
4. **Verify** - Run tests
5. **Document** - Update session_handoff.md

### Session End

```bash
# 1. Run full test suite
pytest tests/ -v

# 2. Update session_handoff.md with:
#    - What was completed
#    - Current state
#    - Next steps

# 3. Commit if requested (never auto-commit)
```

---

## Security Requirements

| Category | Requirement |
|----------|-------------|
| **Input Validation** | Server-side validation, whitelist approach |
| **SQL Injection** | SQLAlchemy ORM only, parameterized queries |
| **Path Traversal** | Validate paths stay within workspace |
| **Command Injection** | Block dangerous shell commands |
| **Secrets** | NEVER in code, use `.env` (gitignored) |
| **API** | CORS configured, validate Content-Type |

---

## Learnings & Anti-Patterns

### From 2026-01-12 Sessions

| Learning | Anti-Pattern to Avoid |
|----------|----------------------|
| Use `env_file` in Docker | `${VAR:-default}` patterns |
| Reuse root Ollama | Spinning up duplicate Ollama |
| start.sh handles setup | Manual dependency checks |
| **Playwright for UI tests** | **curl/requests for browser testing** |
| pytest+requests for JSON APIs | Ad-hoc curl commands |
| Run from v2/ directory | Running from wrong directory |
| Document in session_handoff.md | Losing session context |
| qwen3:1.7b works fast | qwen3:4b times out (5+ min) |

---

## Quick Troubleshooting

```bash
# Container not starting?
docker compose --env-file .env -f docker/docker-compose.yml logs aider-api

# Ollama not responding? (manual debug only - NOT for tests)
ollama list
ollama ps

# API tests failing?
pytest tests/test_aider_api.py -v -s  # -s shows print output

# UI tests failing? (use Playwright, NOT curl)
pytest tests/e2e/ -v -s               # Run browser tests

# Database issues?
alembic current              # Check migration state
alembic stamp head           # Reset migration tracking
alembic upgrade head         # Apply migrations

# Model not found?
ollama pull qwen3:1.7b

# Playwright not working?
playwright install chromium  # Install browser
```

---

## File Reading Order

When starting a session, read files in this order:

1. `CLAUDE.md` - Directives (this file)
2. `session_handoff.md` - Current state and progress
3. `README.md` - Project overview
4. `.env` - Configuration values
5. `scripts/aider_api.py` - Core API implementation
6. `tests/test_aider_api.py` - Test patterns

<claude-mem-context>
# Recent Activity

<!-- This section is auto-generated by claude-mem. Edit content outside the tags. -->

### Jan 15, 2026

| ID | Time | T | Title | Read |
|----|------|---|-------|------|
| #445 | 10:49 PM | 🔵 | Start Script Orchestrates Complete Stack Initialization with Health Checks | ~725 |
</claude-mem-context>
