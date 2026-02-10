# Session Handoff

**Last Updated:** 2026-02-10
**Branch:** `main`

---

## Next Session TODO

### Expand Agent Memory System - Learn from claude-mem

**Goal:** Study the claude-mem architecture and apply learnings to our agentmem system.

**Reference:** https://docs.claude-mem.ai/architecture/overview

**Tasks:**
1. Analyze claude-mem's progressive disclosure pattern (Index -> Timeline -> Details)
2. Compare their chunking/observation boundaries to our tool-attempt approach
3. Study their classification system vs our rule-based (golden/gotcha/discovery/routine)
4. Evaluate their retention/pruning strategies
5. Document what we can adopt for our stack (PostgreSQL + pgvector + Ollama)

**Key Questions to Answer:**
- How does claude-mem handle context injection on failures?
- What additional observation metadata would improve retrieval?
- How do they balance token budgets in progressive disclosure?
- Can we add timeline views for session browsing?

**Our Current Stack:**
- `forge/agentmem/` - Agent-agnostic memory library
- PostgreSQL + pgvector for storage/search
- Ollama nomic-embed-text for embeddings (via main-api:8002)
- Rule-based classifier (no LLM cost)
- Background worker for async processing
- Claude Code hook for observation capture

---

## Pending (2026-02-09)

- User will expand Linux partition from ~100GB to ~300GB via Windows shrink + Live USB (GParted).
- Hibernation requested: add ~64GB swap partition (not 256GB).
- After expansion: enable swap, set resume UUID in GRUB/initramfs.
- Cleaned up root-level markdown files: synced architecture trees, consolidated model info to llm.md, archived old session entries.

---

## Latest Update (2026-02-08)

- Added Docker permission-denied guidance to `start.sh` with explicit steps (`usermod`, `newgrp`) to fix socket access issues.
- Removed unsupported top-level `env_file` from `docker/docker-compose.yml` to satisfy `docker compose` validation.
- Added startup automation defaults in `.env` and dynamic VRAM/disk-guard + auto-pull logic in `start.sh`.
- `docker/docker-compose.yml` now reads `OLLAMA_MAX_VRAM` from env (override via `start.sh` detection).
- Added Proactivity Protocol to `AGENTS.md`.

## Latest Update (2026-02-10)

- Switched default model to `hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M` across configs/docs.
- Updated defaults in `.env`, `start.sh`, `install.sh`, `AGENTS.md`, `README.md`, `llm.md`, and Forge defaults.
- Added model context entry for Qwen3-VL 4B GGUF in `forge/agent/session.py`.
- Updated vision default in `scripts/mcp_vision_server.py`.
- Ran `./start.sh --no-browser` to bring containers up; Ollama auto-pull still downloading `qwen2.5-coder:3b` (Q4) at last check.
- Attempted `pip install -r requirements.txt` but aborted due to long dependency backtracking.
- `pytest tests/ -v` completed with extensive failures/errors (services/health/Playwright/integration); see latest run output.
- `ruff check .` could not run because `ruff` not installed in `venv`.

---

## Implementation Status (2026-02-07 - Agent Memory Session)

### Completed - Agent Memory System (`forge/agentmem/`)

**Core Library:**
- [x] `forge/agentmem/models.py` - Observation dataclass + SQLAlchemy model
- [x] `forge/agentmem/store.py` - DB operations (insert, update, delete, query)
- [x] `forge/agentmem/classifier.py` - Rule-based classification (golden/gotcha/discovery/routine)
- [x] `forge/agentmem/embedder.py` - Embedding via main-api -> Ollama
- [x] `forge/agentmem/retrieval.py` - Cosine similarity search with hybrid filtering
- [x] `forge/agentmem/worker.py` - Background processor for pending observations
- [x] `forge/agentmem/cli.py` - CLI commands (forge mem process/search/stats/pending)

**Hooks:**
- [x] `forge/hooks/observe.py` - Forge post-hook for tool capture
- [x] `.claude/hooks/agentmem_observe.py` - Claude Code post-hook integration
- [x] Updated `.claude/settings.local.json` - Registers hook for Bash/Read/Write/Edit/Grep/Glob

**Database:**
- [x] `alembic/versions/i9j0k1l2m3n4_add_observations.py` - observations table with pgvector
- [x] Added `EMBEDDING_API_BASE` and `EMBEDDING_MODEL` to `.env`

**Tests:**
- [x] `tests/test_agentmem.py` - 14 unit tests (all passing)
- [x] `tests/test_agentmem_integration.py` - 14 integration tests (13 passed, 1 skipped)

### Observation Types
| Type | Keep? | Detection |
|------|-------|-----------|
| `golden` | YES | Multiple attempts -> success (hard-won pattern) |
| `gotcha` | YES | Error that taught something |
| `discovery` | YES | First use of tool in session |
| `routine` | DELETE | Repeated identical success |

### Architecture
```
Tool Call -> [observe hook] -> INSERT (embedding=NULL)
                                    |
              [background worker] -> classify + embed -> UPDATE
                                    |
Tool Failure -> [context_inject] -> search golden patterns -> inject hints
```

---

## Implementation Status (2026-02-05/06 - Hybrid Search & Hook Chain)

### Completed
- [x] Hook chain refinement - renamed for alphabetical execution order
  - `a_prompt_refine.py` - Refines prompts before search
  - `b_context_inject.py` - Injects RAG context using refined prompt
- [x] Hybrid search implementation (PostgreSQL full-text + pgvector)
- [x] Migration: `h8i9j0k1l2m3_add_fulltext_search.py`
- [x] Fixed database collation version mismatch
- [x] Created `docker/init-db.sql` for new installs
- [x] Added `memory_store` and `memory_search` tools to `scripts/agent_cli.py`

### Search Modes
| Mode | Use Case | Example |
|------|----------|---------|
| `text` | Fast keyword search | `memory.search(query="pytest", mode="text")` |
| `embedding` | Semantic similarity | `memory.search(embedding=emb, mode="embedding")` |
| `hybrid` | Combined scoring (default) | `memory.search(query="run tests", embedding=emb)` |

### Hook Chain Order
```
User Prompt -> [a_prompt_refine] -> Refined Prompt -> [b_context_inject] -> Context + Refined Prompt -> LLM
```

---

## Archive

- Pre-2026-02-05 sessions: `logs/session_archive_2026-02-05.md`
- Pre-2026-01-30 sessions: `logs/session_archive_2026-01-30.md`
