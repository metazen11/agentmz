# Session Notes (auto)
- Goal: Fix startup scripts (start.ps1/start.bat/start.sh) so they don't fail on alembic output and browser launches reliably.
- Observed: start.bat exits during alembic upgrade step (NativeCommandError), preventing browser open.
- Services running: wfhub-v2-caddy, wfhub-v2-main-api, wfhub-v2-aider-api, wfhub-v2-ollama, wfhub-v2-db.
