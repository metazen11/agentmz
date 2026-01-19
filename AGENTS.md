# Repository Guidelines

## Project Structure & Module Organization
This repository is a Python-based agentic workflow hub. Key paths:
- `main.py`, `director.py`, `database.py`, `models.py`: FastAPI app, orchestration loop, and SQLAlchemy models.
- `agent/`: agent tooling (e.g., Aider/Ollama runners and file tools).
- `scripts/`: operational scripts (API wrappers, orchestration helpers).
- `alembic/` + `alembic.ini`: database migrations.
- `static/` and `chat.html`: web UI assets.
- `tests/`: pytest + Playwright suites (`test_*.py`).
- `docker/` and `start.sh`: local stack for DB/Ollama/Aider API.
- `workspaces/`: per-project workspaces used by the agent runtime.

## Build, Test, and Development Commands
- `./start.sh`: start the full local stack (Docker + services) and set a workspace (e.g., `./start.sh -w poc`).
- `docker compose --env-file .env -f docker/docker-compose.yml up -d`: run services manually.
- `python scripts/aider_api.py`: start the Aider API service.
- `python main.py`: start the FastAPI app on the configured port.
- `pytest tests/ -v`: run the full test suite.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, `snake_case` for modules/functions and `PascalCase` for classes.
- Ruff configuration in `pyproject.toml` (line length 100). Use `ruff check .` before pushing.
- Keep API schemas in Pydantic models near the endpoints, and keep SQLAlchemy models in `models.py`.

## Testing Guidelines
- Frameworks: `pytest` and `pytest-playwright`.
- Tests live in `tests/` and follow `test_*.py` naming.
- Prefer end-to-end tests for UI flows and direct unit tests for helper modules.

## Commit & Pull Request Guidelines
- Commit messages follow a conventional pattern seen in history: `feat: ...`, `fix: ...`, `test: ...`.
- PRs should include a clear description, test coverage notes (commands run), and screenshots for UI changes.

## Agent-Specific Startup Request
- At session start, read all root-level `*.md` files (e.g., `README.md`, `CLAUDE.md`, `session_handoff.md`) and summarize any coding or workflow principles before making changes.

## Coding Principles Summary
- Prefer small, well-scoped changes; avoid sweeping refactors unless requested.
- Keep dependencies minimal and align with existing patterns in the FastAPI/SQLAlchemy stack.
- Favor explicit error handling and clear logging in orchestration and API paths.
- Maintain testability: add or update tests when behavior changes.
- DRY is mandatory: avoid duplicate logic and consolidate shared behavior.

## Configuration & Data
- Configuration lives in `.env` (e.g., `DATABASE_URL`, `AIDER_API_PORT`); avoid committing secrets.
- Workspace data under `workspaces/` is runtime state; keep changes scoped to specific tasks.
