# Session Notes (auto)
- Goal: Fix startup scripts (start.ps1/start.bat/start.sh) so they don't fail on alembic output and browser launches reliably.
- Observed: start.bat exits during alembic upgrade step (NativeCommandError), preventing browser open.
- Services running: wfhub-v2-caddy, wfhub-v2-main-api, wfhub-v2-aider-api, wfhub-v2-ollama, wfhub-v2-db.
- Current request: add LangGraph persistent memory (Postgres) to LangChain CLI, scope per project, retention by age; document status; commit/push.
- Repo state: modified `scripts/langchain_cli.py`, `requirements.txt`, `README.md`; deleted `=42.0.0`; untracked `.venv312/`, `venv/`, `workspaces/poc`.
- Updated: renamed CLI to `scripts/agent_cli.py`, added `.env` defaults, switched memory scope to project name, added tests.
- Defaults: Agent CLI now uses `https://wfhub.localhost/ollama` and LangGraph enabled by default in `.env.example`.
- Default project name for Agent CLI set to `poc`.
