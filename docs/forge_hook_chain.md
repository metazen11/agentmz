# Forge Hook Chain: Prompt Refinement + RAG

**Date:** 2026-02-02

---

## Overview

Forge uses a pre-hook chain to enhance user prompts before sending to the LLM:

```
User Prompt
    │
    ▼
┌─────────────────────┐
│  a_prompt_refine    │  ← Adds specifications & conventions
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  b_context_inject   │  ← Searches embeddings with REFINED prompt
└─────────────────────┘        │
    │                          ▼
    │                    ProjectMemory
    │                    (pgvector search)
    ▼
┌─────────────────────┐
│  Final Prompt       │  ← Context + Refined Prompt
│  to LLM             │
└─────────────────────┘
```

---

## Hook Execution Order

Hooks are loaded alphabetically by filename:

| Order | File | Type | Purpose |
|-------|------|------|---------|
| 1 | `a_prompt_refine.py` | pre-hook | Refine prompt with specs |
| 2 | `auto_embed.py` | post-hook | Generate embeddings |
| 3 | `auto_log.py` | post-hook | Log tool calls |
| 4 | `b_context_inject.py` | pre-hook | Inject RAG context |
| 5 | `confirm_destructive.py` | pre-hook | Warn on destructive ops |

---

## Example Flow

### Input
```
Add user authentication
```

### After `a_prompt_refine` (Step 1)
```markdown
## Task
Add user authentication

## Requirements
- Determine the appropriate file location based on existing project structure
- Match existing code style and patterns
- Include unit tests if adding new functionality

## Project Conventions
### MUST DO
1. Read before writing
2. Tests first (TDD)
3. Run `pytest` and verify all tests pass before presenting code
...
```

### Knowledge Lookup (Step 2)
The **refined prompt** is used to search embeddings:
- Query: "## Task\nAdd user authentication\n## Requirements..."
- Better semantic match than just "Add user authentication"
- Finds more relevant code snippets

### Final Prompt to LLM (Step 3)
```markdown
## Relevant Context from Project Knowledge

### auth/service.py
class AuthService:
    def login(self, username, password): ...
    def logout(self, session_id): ...

### models/user.py
class User(Base):
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)

---

## User Request

## Task
Add user authentication

## Requirements
- Determine the appropriate file location based on existing project structure
- Match existing code style and patterns
- Include unit tests if adding new functionality

## Project Conventions
...
```

---

## Why This Order?

1. **Refined prompt → Better search**: Adding specifications to the query improves embedding similarity search. "Add user authentication" alone might match generic content, but with requirements like "Match existing code style", the search finds more relevant existing code.

2. **Context first**: The LLM sees relevant codebase context before the task, helping it understand existing patterns before generating new code.

3. **Conventions included**: Project-specific rules (from AGENTS.md) are included so the LLM follows them automatically.

---

## Prompt Type Detection

`a_prompt_refine` detects prompt types and adds appropriate requirements:

| Detected Type | Keywords | Added Requirements |
|---------------|----------|-------------------|
| Code Generation | add, create, implement, write, build | File location, code style, unit tests |
| Bug Fix | fix, bug, error, broken, issue | Root cause analysis, regression prevention |
| Refactoring | refactor, improve, optimize, clean | Maintain behavior, minimal changes |
| Questions | what, how, why, explain, ? | (No changes - passed through) |

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENTS_MD_PATH` | `AGENTS.md` | Path to conventions file |
| `EMBEDDING_API_BASE` | `http://localhost:8002` | Embedding endpoint |
| `RAG_MAX_CONTEXT_TOKENS` | `2000` | Max context to inject |
| `RAG_MIN_SIMILARITY` | `0.3` | Minimum similarity threshold |

### Custom Conventions

```python
from forge.hooks.a_prompt_refine import set_conventions

set_conventions("""
- Use TypeScript
- Follow DRY principle
- Write comprehensive tests
""")
```

---

## Testing

```bash
# Run all hook tests
python -m pytest tests/test_forge_integration.py -v

# Run specific test classes
python -m pytest tests/test_forge_integration.py::TestPromptRefine -v
python -m pytest tests/test_forge_integration.py::TestContextInject -v
python -m pytest tests/test_forge_integration.py::TestHookChainOrder -v
```

Expected: 38 passed

---

## Search Modes

ProjectMemory supports three search modes:

| Mode | Use Case | Speed | Accuracy |
|------|----------|-------|----------|
| `text` | Keyword search, exact terms | Fast | Good for exact matches |
| `embedding` | Semantic similarity | Slower | Best for meaning |
| `hybrid` | Combined text + embedding | Medium | Best overall |

```python
# Text-only (fast, no embedding needed)
memory.search(query="pytest", mode="text")

# Embedding-only (semantic)
memory.search(query="", embedding=emb, mode="embedding")

# Hybrid (default - best of both)
memory.search(query="run tests", embedding=emb, mode="hybrid")
```

---

## Files

| File | Purpose |
|------|---------|
| `forge/hooks/a_prompt_refine.py` | Prompt refinement pre-hook |
| `forge/hooks/b_context_inject.py` | RAG context injection pre-hook |
| `forge/hooks/auto_embed.py` | Embedding generation post-hook |
| `forge/memory/store.py` | ProjectMemory with hybrid search |
| `tests/test_forge_integration.py` | Integration tests (38 tests) |
| `alembic/versions/h8i9j0k1l2m3_*.py` | Migration for tsvector + HNSW index |
