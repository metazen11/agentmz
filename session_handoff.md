# Session Handoff

**Last Updated:** 2026-02-06
**Branch:** `feat/langchain-orchestration`

---

## Implementation Status (2026-02-06 - Latest Session)

### Completed
- [x] Hook chain refinement - renamed for alphabetical execution order
  - `a_prompt_refine.py` - Refines prompts before search
  - `b_context_inject.py` - Injects RAG context using refined prompt
- [x] Hybrid search implementation (PostgreSQL full-text + pgvector)
- [x] Migration: `h8i9j0k1l2m3_add_fulltext_search.py`
- [x] Fixed database collation version mismatch
- [x] Created `docker/init-db.sql` for new installs
- [x] Added `memory_store` and `memory_search` tools to `scripts/agent_cli.py`
- [x] Prompter workspace structure (partially started)

### Git Recovery Required

**Issue:** Git repo corrupted (missing HEAD, corrupted tree objects)

**Backup location:** `~/Dropbox/_coding/agentmz-backup-2026-02-06/`

Contents:
- `agent_cli.py` - memory tools + system message
- `hooks/` - a_prompt_refine.py, b_context_inject.py, auto_embed.py
- `memory/` - store.py with hybrid search
- `g7h8i9j0k1l2_add_project_knowledge.py` - alembic migration
- `h8i9j0k1l2m3_add_fulltext_search.py` - alembic migration
- `init-db.sql` - docker init script

**Recovery steps:**
```bash
cd ~/Dropbox/_coding
git clone https://github.com/metazen11/agentmz.git
cd agentmz

# Copy backup files
cp ../agentmz-backup-2026-02-06/agent_cli.py scripts/
cp -r ../agentmz-backup-2026-02-06/hooks forge/
cp -r ../agentmz-backup-2026-02-06/memory forge/
cp ../agentmz-backup-2026-02-06/*.py alembic/versions/
cp ../agentmz-backup-2026-02-06/init-db.sql docker/

# Setup venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment Notes
- Windows venv (`.venv312`) doesn't work in WSL
- User switching to native Linux which should resolve this

### Next Steps
1. Complete git recovery
2. Test Forge CLI with memory tools
3. Create daily logs structure: `/logs/claude-YYYY-MM-DD.log`
4. Add per-project `/logs/` and `/memory/` directories
5. Continue Prompter data model implementation

### Reference: OpenClaw Agent Loop
https://docs.openclaw.ai/concepts/agent-loop
Similar patterns to Forge: hook-based extensibility, event streaming, session serialization

---

## Project Overview

**wfhub-v2** - Workflow Hub with Aider/Ollama integration for agentic coding

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

**Phase 2: Tooling & Hooks** ✅ (Core complete)
- [x] Pre/Post hook system (`forge/hooks/`)
- [x] HookManager class with pre_tool/post_tool methods
- [x] Pre-hook: Confirmation for destructive ops (`confirm_destructive.py`)
- [x] Post-hook: Tool execution logging (`auto_log.py` -> `~/.forge/tool_history.jsonl`)
- [ ] Tool display in collapsible panels (TUI enhancement)
- [ ] Syntax highlighting for file diffs (TUI enhancement)

**Phase 3: Project Memory (pgvector)** ✅ (Core complete)
- [x] Add pgvector extension to Postgres (`docker-compose.yml` -> `pgvector/pgvector:pg16`)
- [x] Create `project_knowledge` table with embeddings (Alembic migration)
- [x] ProjectMemory class (`forge/memory/store.py`)
- [ ] Retrieve relevant context before LLM call (integration pending)
- [ ] Store successful solutions (integration pending)

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
| `forge/hooks/__init__.py` | HookManager for pre/post tool hooks |
| `forge/hooks/confirm_destructive.py` | Warn on destructive operations |
| `forge/hooks/auto_log.py` | Log tool calls to ~/.forge/tool_history.jsonl |
| `forge/memory/store.py` | ProjectMemory for semantic search |
| `scripts/agent_cli.py` | LangGraph agent with tools |

---

## Implementation Status (2026-02-01 - Orchestration Session)

### Completed

**Subagent Orchestration Experiment** ✅
- [x] Tested Codex CLI (`codex exec --full-auto`) for code generation
- [x] Tested Gemini CLI (`gemini -p --yolo`) for analysis
- [x] Created orchestration guide (`docs/subagent_orchestration.md`)
- [x] Documented best practices for delegation

**AGENTS.md Improvements** ✅
- [x] Updated Rules of Engagement with active testing/security verbs
- [x] Changed session-init hook to reminder mode (tells agent to read file)

### New Files Created
| File | Purpose |
|------|---------|
| `docs/forge_architecture.md` | Codex-generated architecture reference |
| `docs/subagent_orchestration.md` | Guide for using Codex/Gemini as subagents |
| `forge/hooks/__init__.py` | HookManager class |
| `forge/hooks/confirm_destructive.py` | Pre-hook for destructive ops |
| `forge/hooks/auto_log.py` | Post-hook for tool logging |
| `forge/memory/__init__.py` | Memory module init |
| `forge/memory/store.py` | ProjectMemory class |
| `alembic/versions/g7h8i9j0k1l2_add_project_knowledge.py` | Migration for pgvector |

### Orchestration Learnings
- **Codex** (gpt-5.1-codex-mini): Good for file ops, code generation, project exploration
- **Gemini**: Good for analysis, documentation, research
- **Claude** (orchestrator): Should delegate, review, integrate - not code directly
- Specific prompts with file paths and constraints work best
- Always capture output for review before proceeding

---

## Implementation Status (2026-02-01 - Embedding API)

### Completed
- [x] Codex added `/api/embeddings` endpoint to main.py
- [x] Added `EMBEDDING_MODEL=nomic-embed-text` to .env
- [x] Pulled nomic-embed-text model to Ollama container
- [x] Endpoint uses OLLAMA_PROXY_TARGET for container-to-container calls

### Pending - Requires Container Restart
- [ ] Restart main-api container to load new code
- [ ] Test embedding endpoint: `curl -X POST http://localhost:8002/api/embeddings -d '{"text": "test"}'`
- [ ] Update forge/memory/store.py to call /api/embeddings for vector generation
- [ ] Rebuild db container to use pgvector image
- [ ] Run migration: `alembic upgrade head`

### Architecture
```
User Request -> Forge Agent -> LLM
                    |
                    v
           ProjectMemory.search()
                    |
                    v
           /api/embeddings (main-api)
                    |
                    v
           Ollama nomic-embed-text
                    |
                    v
           pgvector similarity search
                    |
                    v
           Context injected into LLM prompt
```

---

## Principles

- **TDD**: Write tests first
- **DRY**: Use existing code
- **Stay Focused**: One task at a time
- **Graceful Failure**: Try/except with structured errors
- **Structured JSON**: `{"success": true, ...}` format

## Implementation Status (2026-02-02 - Integration Testing)

### Completed
- [x] Added `tests/test_forge_integration.py` covering hook behavior, embedding endpoint responses, and memory persistence helpers
- [x] Introduced fake session/db helpers so ProjectMemory tests validate logic without needing a live PostgreSQL/pgvector instance
- [x] Mocked Ollama responses so `/api/embeddings` tests stay fast and deterministic

### Files touched
| File | Purpose |
|------|---------|
| `tests/test_forge_integration.py` | Consolidated hook, embedding, and ProjectMemory integration tests |

---

## Implementation Status (2026-02-01 - RAG Hooks)

### Completed
- [x] Created `forge/hooks/auto_embed.py` - Post-hook for automatic embedding generation
- [x] Created `forge/hooks/context_inject.py` - Pre-hook for RAG context injection
- [x] Added `prune()`, `stats()` methods to ProjectMemory for knowledge base maintenance
- [x] Added 15 new tests for hooks and prune functionality
- [x] All 27 integration tests pass

### New Files
| File | Purpose |
|------|---------|
| `forge/hooks/auto_embed.py` | Auto-generate embeddings for stored content |
| `forge/hooks/context_inject.py` | Inject relevant context before LLM calls |
| `docs/forge_rag_verification_report.md` | Full test report with verification commands |

### RAG Architecture
```
User Request → [context_inject] → Enhanced Prompt → LLM → Tool → [auto_embed] → ProjectMemory
                                                                                    ↓
                                                                             [prune - periodic]
```

### Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBEDDING_API_BASE` | `http://localhost:8002` | Embedding endpoint |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Default model |
| `RAG_MAX_CONTEXT_TOKENS` | `2000` | Max context tokens |
| `FORGE_PROJECT_ID` | `1` | Default project ID |

### Verification Command
```bash
source venv/bin/activate && python -m pytest tests/test_forge_integration.py -v
# Expected: 27 passed
```

---

## Implementation Status (2026-02-02 - Prompt Refinement Hook)

### Completed
- [x] Created `forge/hooks/a_prompt_refine.py` - Pre-hook for prompt refinement
- [x] Renamed hooks for execution order: `a_prompt_refine` → `b_context_inject` → others
- [x] Added 11 new tests for prompt_refine and hook chain order
- [x] All 38 integration tests pass

### Hook Chain Order
```
User Prompt → [a_prompt_refine] → Refined Prompt → [b_context_inject] → Context + Refined Prompt → LLM
```

### New/Renamed Files
| File | Purpose |
|------|---------|
| `forge/hooks/a_prompt_refine.py` | Refine prompts with specs and conventions (runs first) |
| `forge/hooks/b_context_inject.py` | Inject RAG context (runs second, uses refined prompt) |

### Prompt Refinement Features
- Detects prompt type: code generation, bug fix, refactor, questions
- Adds task-specific requirements automatically
- Loads project conventions from AGENTS.md
- Stores original prompt for reference (`_original_prompt`)
- Questions are passed through unchanged

### Verification Command
```bash
source venv/bin/activate && python -m pytest tests/test_forge_integration.py -v
# Expected: 38 passed
```

---

## Implementation Status (2026-02-05 - Hybrid Search)

### Completed
- [x] Added PostgreSQL full-text search (tsvector) to project_knowledge
- [x] Created HNSW index for fast vector similarity search
- [x] Implemented hybrid search combining text + embedding scores
- [x] Fixed database collation version mismatch
- [x] Added init-db.sql for new installs

### Migration
```bash
alembic upgrade head  # Runs h8i9j0k1l2m3_add_fulltext_search
```

### Search Modes
| Mode | Use Case | Example |
|------|----------|---------|
| `text` | Fast keyword search | `memory.search(query="pytest", mode="text")` |
| `embedding` | Semantic similarity | `memory.search(embedding=emb, mode="embedding")` |
| `hybrid` | Combined scoring (default) | `memory.search(query="run tests", embedding=emb)` |

### Files Changed
| File | Changes |
|------|---------|
| `forge/memory/store.py` | Added hybrid search with tsvector + vector |
| `alembic/versions/h8i9j0k1l2m3_*.py` | Migration for tsvector column + HNSW index |
| `docker/init-db.sql` | Database init script for new installs |
| `docker/docker-compose.yml` | Added env_file and init script mount |

---

## Archive

Full session history archived to: `logs/session_archive_2026-01-30.md`
