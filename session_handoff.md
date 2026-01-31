# Session Handoff

**Last Updated:** 2026-01-31
**Branch:** `feat/langchain-orchestration` (merged to main)

---

## Project Overview

**wfhub-v2** - Workflow Hub with Aider/Ollama integration for agentic coding.

### Architecture
```
├── main.py                 # FastAPI CRUD + WebSocket logs (port 8002)
├── scripts/
│   ├── aider_api.py        # Coding tools + agent orchestration (port 8001)
│   └── agent_cli.py        # LangGraph CLI agent
├── forge/                  # TUI for agent interaction
│   ├── app.py              # Textual TUI
│   ├── cli.py              # CLI with yolo mode
│   └── agent/runner.py     # Agent wrapper
├── docker/
│   └── docker-compose.yml  # 4 services: db, ollama, main-api, aider-api
└── workspaces/             # Project workspaces (each has own git)
```

### Services
| Container | Port | Purpose |
|-----------|------|---------|
| wfhub-v2-db | 5433 | PostgreSQL |
| wfhub-v2-ollama | 11435 | Ollama LLM |
| wfhub-v2-main-api | 8002 | CRUD + WebSocket logs |
| wfhub-v2-aider-api | 8001 | Coding tools + agent |

### Quick Start
```bash
./start.sh                    # Start all services
forge                         # Launch TUI
forge -p "Create hello.html"  # Yolo mode
```

---

## Implementation Status (2026-01-30)

### Completed
- [x] Added Forge runner wrapper (`scripts/forge_runner.py`)
- [x] Added deterministic Forge model tests (HTML5 + JS)
- [x] Added deterministic knobs in agent_cli.py (temperature/seed)
- [x] Documented Forge test env vars in `.env.example`

---

## Implementation Status (2026-01-30 - Forge TUI Session)

### Completed - Forge TUI (Phase 1 + Phase 4)

**Phase 1: Core Loop (MVP)** ✅
- [x] `/forge` directory structure with all widgets
- [x] CLI with yolo mode (`forge -p "prompt"`)
- [x] TUI with single-panel chat display
- [x] Agent wrapper (runner.py) with streaming support
- [x] Key bindings: Ctrl+C quit, Ctrl+L clear, Up/Down history, Esc cancel
- [x] Status bar with FORGE branding, workspace, model display
- [x] Clipboard copy/paste (Ctrl+Y/Ctrl+V) with WSL/Mac/Linux support
- [x] Command palette (Ctrl+P), Help (F1)
- [x] Built-in commands that bypass LLM: cd, pwd, ls, model, clear, help
- [x] Shell pass-through: cp, mv, rm, mkdir, touch, cat, head, tail, grep, git, curl
- [x] Tool aliases for common LLM mistakes (rename_file→move_file, etc.)
- [x] Argument normalization (old_name/new_name→src/dst)
- [x] Respond tool for conversational replies

**Phase 4: @ File Completion** ✅
- [x] Autocomplete triggers on `@` character
- [x] Fuzzy file search in workspace
- [x] Tab/Enter to select from dropdown
- [x] @ stripped from paths before sending to LLM

### Remaining - Forge TUI

**Phase 2: Tooling & Hooks** ❌
- [ ] Pre/Post hook system (`hooks/` directory)
- [ ] Pre-hook: Confirmation for destructive ops
- [ ] Post-hook: Auto-commit, notification, logging
- [ ] Tool display in collapsible panels
- [ ] Syntax highlighting for file diffs

**Phase 3: Project Memory (pgvector)** ❌
- [ ] Add pgvector extension to Postgres
- [ ] Create `project_knowledge` table with embeddings
- [ ] Retrieve relevant context before LLM call
- [ ] Store successful solutions

**Phase 5: /config Command** ✅
- [x] Settings panel (model selection, workspace, hooks)
- [x] Auto-discover models from Ollama (`/config list-models`)
- [x] Persistence in `~/.forge/config.toml`
- [x] Available in both CLI and TUI

**Phase 6: Forge as Subagent** ✅ (Partial)
- [x] Subagent wrapper (`forge/subagent.py`)
- [x] Tool registry for dynamic tools (`forge/tools/registry.py`)
- [x] Session manager with token tracking (`forge/agent/session.py`)
- [x] Tested: qwen3-vl:8b works (30s response, native tool calling)
- [ ] Self-improving: Forge adds its own tools (scaffolded)
- [ ] Two-agent coordination (Claude + Forge)

### Key Files
| File | Purpose |
|------|---------|
| `forge/app.py` | Textual TUI app |
| `forge/cli.py` | Typer CLI with yolo mode |
| `forge/config.py` | /config command + TOML persistence |
| `forge/agent/runner.py` | Agent wrapper with tool aliases |
| `forge/agent/session.py` | Session manager with token tracking |
| `forge/subagent.py` | Claude Code delegation wrapper |
| `forge/tools/registry.py` | Dynamic tool registry |
| `forge/widgets/file_autocomplete.py` | @ file completion |
| `scripts/agent_cli.py` | LangGraph agent with tools |

---

## Principles

- **TDD**: Write tests first
- **DRY**: Use existing code
- **Stay Focused**: One task at a time
- **Graceful Failure**: Try/except with structured errors
- **Structured JSON**: `{"success": true, ...}` format

---

## Archive

Full session history archived to: `logs/session_archive_2026-01-30.md`
