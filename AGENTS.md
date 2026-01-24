# Agent Operational Framework

> Canonical reference for all AI agents (Claude, Gemini, Cursor, etc.) working in this repository.
> Version: 4.0 | Single Source of Truth

---

## 0. The Prime Directive

**INTERNALIZE THIS ENTIRE DOCUMENT AT THE START OF EVERY SESSION.**

Your primary directive: Do not merely complete tasks. Enhance the system's integrity, maintainability, and quality. Failure to do so is a failure of your primary function.

---

## 1. Core Axioms of Systems Engineering

These are immutable laws, not guidelines.

1. **Mission Is Paramount** - Understand the 'why' before writing code. Resolve all ambiguity first.

2. **The System Is a Whole** - No component is isolated. Maintain a complete mental model of the repository, architecture, and dependencies.

3. **Resilience Is Non-Negotiable** - All work must be robust, secure, and maintainable:
   - **Single Responsibility:** One purpose per module/class/function
   - **DRY:** No duplicate code. Consolidate shared logic.
   - **Abstraction:** Build system-agnostic solutions where feasible

4. **Success Is Measured, Not Assumed** - All work validated by automated tests. No assumptions.

5. **Standardize** - Eliminate variance. Enforce conventions. Where a standard is absent, create one.

6. **Elegant Solutions** - Simplest path to the objective. Minimize complexity, overhead, and dependencies.

---

## 2. The Engineering Lifecycle

All tasks follow this five-phase model.

### Phase 1: Deconstruction & Discovery (Understand)

1. **Initialize Working Memory:** Use `session_notes.md` as your operational scratchpad
2. **Deconstruct the Request:** Break into discrete, verifiable sub-tasks
3. **Codebase Reconnaissance:** Use glob/grep to identify relevant files
4. **Impact Analysis:** Determine side effects and collateral impacts
5. **Formulate Execution Plan:** Draft changes, tests required, and risks

### Phase 2: Hypothesis & Design (Plan)

1. **Propose the Solution:** Articulate implementation strategy with precision
2. **Test-First Design (TDD):** Write tests that verify the feature/fix. Tests MUST fail before implementation.
3. **Schema Design:** If DB changes needed, define models.py modifications and alembic migration
4. **Confirmation Lock:** Present plan to user. Do NOT proceed without explicit approval.

### Phase 3: Synthesis & Implementation (Execute)

1. **Write Implementation Code:** Minimum viable code to satisfy tests
2. **Strict Adherence to Conventions:** Follow all naming/styling/architectural patterns
3. **Iterate Until Green:** Run tests, fix failures, repeat until all pass

### Phase 4: Verification & Validation (Verify)

1. **Execute Full Test Suite:** `pytest tests/ -v` - a single failure returns you to Phase 3
2. **Quality Checks:** Run `ruff check .` and fix all issues
3. **Integration Verification:** For UI changes, validate with Playwright

### Phase 5: Deployment & Handoff (Deploy)

1. **Update Session Handoff:** Modify `session_handoff.md` with structured report
2. **Propose Commit:** Draft descriptive, conventional commit message
3. **Await Command:** Do NOT commit or push without explicit instruction

---

## 3. Learning Protocol

Every failure is a mandatory lesson.

### Root Cause Analysis (RCA)

On any failure or user correction:
1. **Log the Anomaly:** What was expected vs actual?
2. **Identify Root Cause:** Which axiom was violated? Which assumption was false?
3. **Define Corrective Action:** What prevents this class of error?
4. **Update the Codex:** Record as new anti-pattern entry

### Codex of Anti-Patterns

| Anti-Pattern | Root Cause | Corrective Action |
|--------------|------------|-------------------|
| Using curl/requests for UI testing | HTTP lacks DOM state and JS context | Use Playwright for UI tests. curl is fine for API/health checks only. |
| Hardcoding configuration values | Violation of standardization | Read ALL config from `.env` via config object. Never hardcode. |
| Not running full test suite | Overconfidence in isolated changes | A change is not "done" until `pytest tests/ -v` passes with zero failures. |
| Creating synonym names | Failure of discovery phase | Search codebase first to verify canonical name doesn't exist. |
| Presenting untested code | Skipping verification phase | Run and verify all code before presenting to user. |

---

## 4. Proactive Imperatives

Your value is in initiative, not just obedience.

- **Opportunity Identification:** Log anti-patterns, code smells, and bugs found during work. Present as "Opportunities for Improvement" after completing primary task.
- **Dependency Health Check:** Check for version drift or security vulnerabilities. Report findings.
- **Documentation Enhancement:** Propose corrections for incorrect, misleading, or absent documentation.

---

## 5. Rules of Engagement

### MUST DO
1. Read before writing
2. Tests first (TDD)
3. Verify all tests pass
4. Use canonical names
5. Use structured JSON responses for APIs
6. Validate all inputs
7. Enforce path security
8. Source all config from `.env`
9. Use Alembic for ALL migrations
10. Update `session_handoff.md`
11. Run from project root
12. Keep files small (<500 lines)

### MUST NOT
1. Skip tests
2. Hardcode configuration
3. Duplicate services
4. Use another ORM (SQLAlchemy only)
5. Make manual DB changes
6. Use string concatenation for SQL
7. Ignore errors
8. Add unrequested features
9. Use curl for UI/functional testing
10. Present untested code

---

## 6. Project Overview

**Workflow Hub v2** - Minimal agentic task orchestration with AI-powered code editing.

| Attribute | Value |
|-----------|-------|
| **Stack** | FastAPI + SQLAlchemy + PostgreSQL + Aider + Ollama |
| **Database** | PostgreSQL 16 (port 5433) |
| **Models** | qwen3:1.7b (code), qwen3:4b (general) |
| **Container Runtime** | Docker Compose |

---

## 7. Architecture

```
v2/
├── .env                      # ALL configuration (single source of truth)
├── start.sh                  # Startup script
├── AGENTS.md                 # THIS FILE - canonical agent directives
├── session_handoff.md        # Session state tracking
│
├── main.py                   # FastAPI app entry point
├── director.py               # Orchestration loop
├── models.py                 # SQLAlchemy models (Project, Task)
├── database.py               # Database connection
│
├── agent/                    # Agent tooling (Aider/Ollama runners, file tools)
├── scripts/
│   └── aider_api.py          # Coding Agent HTTP API (core service)
│
├── docker/
│   ├── docker-compose.yml    # Container orchestration
│   └── Dockerfile.aider-api  # Aider API container
│
├── alembic/                  # Database migrations
│   └── versions/
│
├── tests/                    # pytest + Playwright test suites
│   ├── test_aider_api.py     # API endpoint tests
│   └── test_*.py             # Other tests
│
├── static/                   # Web UI assets
├── chat.html                 # Web UI
│
└── workspaces/               # Project workspaces (mounted to containers)
    └── poc/                  # Default workspace
```

---

## 8. API Endpoints

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

## 9. Naming Conventions

> ONE correct name per concept. Use it EVERYWHERE.

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

---

## 10. Configuration

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

---

## 11. Database & Migrations

### SQLAlchemy Models

All models defined in `models.py`. Key entities:

```python
class Project(Base):
    __tablename__ = "projects"
    id: int (PK)
    name: str
    workspace_path: str
    created_at: datetime

class Task(Base):
    __tablename__ = "tasks"
    id: int (PK)
    project_id: int (FK -> projects.id)
    prompt: str
    status: str  # pending, running, completed, failed
    result: str (nullable)
    created_at: datetime
```

### Migration Commands

```bash
alembic upgrade head                          # Apply all migrations
alembic revision --autogenerate -m "desc"     # Create new migration
alembic current                               # Check current version
alembic history                               # View migration history
alembic stamp head                            # Mark as current (skip migrations)
alembic downgrade -1                          # Rollback one migration
```

### Migration Best Practices

1. Always create migrations for schema changes (never manual ALTER TABLE)
2. Review autogenerated migrations before applying
3. Test migrations on a copy of production data when possible
4. Include both upgrade() and downgrade() functions

---

## 12. Testing Standards

### Frameworks
- `pytest` for unit and integration tests
- `pytest-playwright` for end-to-end UI tests

### Test File Organization
```
tests/
├── test_aider_api.py         # API endpoint tests
├── test_database.py          # Database operation tests
├── test_models.py            # Model validation tests
├── test_integration.py       # Cross-component tests
└── e2e/
    └── test_ui_flows.py      # Playwright browser tests
```

### When to Use What

| Test Type | Tool | Use Case |
|-----------|------|----------|
| API endpoints | pytest + requests | JSON API responses, status codes |
| Health checks | curl or pytest | Quick verification |
| Database ops | pytest + SQLAlchemy | CRUD operations, constraints |
| UI interactions | Playwright | Button clicks, form fills, rendered content |
| Full user flows | Playwright | End-to-end scenarios |

### Test Naming Convention
```python
def test_<what>_<condition>_<expected>():
    # Example: test_create_project_with_valid_data_returns_201
    pass
```

### Running Tests
```bash
pytest tests/ -v                              # All tests
pytest tests/test_aider_api.py -v             # Specific file
pytest tests/ -k "test_create"                # Pattern match
pytest tests/ --tb=short                      # Shorter tracebacks
pytest tests/ -x                              # Stop on first failure
```

---

## 13. Code Patterns

### API Endpoint Pattern
```python
@router.post("/api/resource")
async def create_resource(request: ResourceRequest):
    try:
        result = service.create(request)
        return {"success": True, "data": result}
    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"success": False, "error": "Internal server error"}
```

### Database Session Pattern
```python
from database import get_session

def get_projects():
    with get_session() as session:
        return session.query(Project).all()
```

### Configuration Access Pattern
```python
from config import settings

base_url = settings.OLLAMA_API_BASE  # Never hardcode
```

### Error Handling Pattern
```python
def risky_operation(data):
    try:
        result = process(data)
        return {"success": True, "data": result}
    except SpecificError as e:
        logger.warning(f"Expected error: {e}")
        return {"success": False, "error": str(e), "recoverable": True}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"success": False, "error": "Internal error", "recoverable": False}
```

---

## 14. Security Requirements

### Input Validation
- All inputs validated server-side
- Use whitelist approach (allow known-good, reject everything else)
- Validate types, ranges, formats, and lengths

### SQL Injection Prevention
- SQLAlchemy ORM only - never string concatenation
- Parameterized queries for any raw SQL

```python
# CORRECT
session.query(User).filter(User.id == user_id).first()

# WRONG - NEVER DO THIS
session.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

### XSS Prevention
- Escape all user content in templates
- Use framework's built-in escaping

### Path Traversal Prevention
```python
import os

def safe_path(base_dir: str, user_path: str) -> str:
    """Ensure path stays within base directory."""
    full_path = os.path.normpath(os.path.join(base_dir, user_path))
    if not full_path.startswith(os.path.normpath(base_dir)):
        raise ValueError("Path traversal attempt detected")
    return full_path
```

### Secrets Management
- Never commit secrets to code
- Use `.env` file (gitignored)
- Rotate credentials regularly

---

## 15. Quick Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Database connection refused | Docker not running | `docker compose up -d` |
| Port already in use | Previous instance running | `lsof -i :PORT` then kill process |
| Alembic "Target database is not up to date" | Pending migrations | `alembic upgrade head` |
| Alembic "Can't locate revision" | Missing migration file | `alembic stamp head` to reset |
| Ollama model not found | Model not pulled | `ollama pull qwen3:1.7b` |
| Tests fail with import error | Wrong Python environment | `source venv/bin/activate` |
| Permission denied on start.sh | Not executable | `chmod +x start.sh` |
| Docker volume issues | Stale data | `docker compose down` (NOT `-v`!) then `up -d` |

---

## 16. Quick Reference Commands

```bash
# === STARTUP ===
cd <project-root>                             # Navigate to project root
./start.sh                                    # Linux/Mac/WSL
# Windows: use PowerShell or run Docker commands manually

# === TESTING ===
pytest tests/ -v                              # All tests
pytest tests/test_aider_api.py -v             # API tests only
ruff check .                                  # Linting

# === DOCKER ===
docker compose --env-file .env -f docker/docker-compose.yml up -d      # Start
docker compose --env-file .env -f docker/docker-compose.yml down       # Stop (keeps data)
docker compose --env-file .env -f docker/docker-compose.yml logs -f    # Logs
docker compose --env-file .env -f docker/docker-compose.yml build      # Rebuild

# === DATABASE ===
alembic upgrade head                          # Apply migrations
alembic revision --autogenerate -m "desc"     # Create migration
alembic current                               # Check status
```

---

## 17. Session Startup Protocol

When starting a session, read files in this order:

1. `AGENTS.md` - This file (operational framework)
2. `session_handoff.md` - Current state and progress
3. `README.md` - Project overview (if exists)
4. `.env` - Configuration values
5. Relevant source files for the task at hand
