import json

import pytest
import httpx
from httpx import HTTPStatusError, Request, ASGITransport, AsyncClient

from forge.hooks import HookManager, auto_log, confirm_destructive
from forge.memory.store import ProjectMemory
import main


class _FakeEmbeddingResponse:
    def __init__(self, *, vector=None, status_code=200, text=None):
        self.status_code = status_code
        self._vector = vector or []
        self._text = text or json.dumps({"embedding": self._vector})
        self.request = Request("POST", "http://testserver/api/embeddings")

    def json(self):
        return {"embedding": self._vector}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPStatusError("Ollama error", request=self.request, response=self)

    @property
    def text(self):
        return self._text


class _FakeResult:
    def __init__(self, rows=None, insert_id=None):
        self._rows = rows or []
        self._insert_id = insert_id

    def scalar(self):
        return self._insert_id

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, database):
        self._database = database

    def execute(self, statement, params):
        sql = getattr(statement, "text", str(statement)).lower()
        if "insert into project_knowledge" in sql:
            return _FakeResult(insert_id=self._database.insert(params))
        if "select id" in sql and "project_knowledge" in sql:
            return _FakeResult(rows=self._database.search(params))
        if "delete from project_knowledge" in sql:
            self._database.delete(params)
            return _FakeResult(rows=[])
        raise ValueError("Unexpected SQL executed")

    def commit(self):
        pass

    def close(self):
        pass


class _FakeProjectKnowledgeDB:
    def __init__(self):
        self.records = []

    def insert(self, params):
        metadata = json.loads(params["extra_data"]) if params.get("extra_data") else None
        record_id = len(self.records) + 1
        record = {
            "id": record_id,
            "project_id": params["project_id"],
            "content_type": params["content_type"],
            "file_path": params.get("file_path"),
            "content": params["content"],
            "summary": params.get("summary"),
            "extra_data": metadata,
            "embedding": params.get("embedding"),
        }
        self.records.append(record)
        return record_id

    def search(self, params):
        pattern = (params.get("pattern") or "").strip("%").lower()
        limit = params.get("limit", len(self.records))
        target_type = params.get("content_type")
        matches = []
        for record in reversed(self.records):
            if record["project_id"] != params.get("project_id"):
                continue
            if target_type and record["content_type"] != target_type:
                continue
            if pattern:
                content_match = pattern in (record["content"] or "").lower()
                summary_match = pattern in (record["summary"] or "").lower()
                if not (content_match or summary_match):
                    continue
            matches.append(record)
            if len(matches) >= limit:
                break
        return [
            (
                record["id"],
                record["content_type"],
                record["file_path"],
                record["content"],
                record["summary"],
                json.dumps(record["extra_data"]) if record["extra_data"] else None,
                0.0,
            )
            for record in matches
        ]

    def delete(self, params):
        project_id = params.get("project_id")
        target_id = params.get("id")
        self.records = [
            record
            for record in self.records
            if not (record["project_id"] == project_id and record["id"] == target_id)
        ]


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def fake_project_memory(monkeypatch):
    db = _FakeProjectKnowledgeDB()

    def _fake_get_session(self):
        return _FakeSession(db)

    monkeypatch.setattr(ProjectMemory, "_get_session", _fake_get_session)
    return db


class TestForgeHooks:
    def test_pre_hook_called_before_tool(self):
        manager = HookManager()
        manager._loaded = True
        manager._pre_hooks = []
        manager._post_hooks = []
        events = []

        def pre_hook(tool_name, args):
            events.append(("pre", tool_name, args.copy()))
            return True

        manager._pre_hooks.append(pre_hook)

        assert manager.pre_tool("apply_patch", {"path": "forge/app.py"})
        events.append(("tool", "apply_patch"))

        assert events == [
            ("pre", "apply_patch", {"path": "forge/app.py"}),
            ("tool", "apply_patch"),
        ]

    def test_pre_hook_can_block_execution(self):
        manager = HookManager()
        manager._loaded = True
        manager._pre_hooks = []
        manager._post_hooks = []
        events = []

        def blocking_pre(tool_name, args):
            events.append(("pre", tool_name))
            return False

        manager._pre_hooks.append(blocking_pre)

        assert manager.pre_tool("delete_file", {"path": "danger.txt"}) is False
        assert events == [("pre", "delete_file")]

    def test_post_hook_called_after_tool(self):
        manager = HookManager()
        manager._loaded = True
        manager._pre_hooks = []
        manager._post_hooks = []
        events = []

        def post_hook(tool_name, args, result):
            events.append(("post", tool_name, args.copy(), result))

        manager._post_hooks.append(post_hook)

        manager.post_tool("write_file", {"path": "k.txt"}, {"success": True})
        events.append(("after", "write_file"))

        assert events == [
            ("post", "write_file", {"path": "k.txt"}, {"success": True}),
            ("after", "write_file"),
        ]

    def test_auto_log_writes_to_file(self, tmp_path):
        original = auto_log.LOG_FILE
        auto_log.LOG_FILE = tmp_path / ".forge" / "tool_history.jsonl"
        try:
            auto_log.post_tool("test_tool", {"path": "notes.txt"}, {"success": True})

            assert auto_log.LOG_FILE.exists()
            lines = auto_log.LOG_FILE.read_text().strip().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["tool"] == "test_tool"
            assert entry["success"] is True
        finally:
            auto_log.LOG_FILE = original

    def test_confirm_destructive_warns_on_delete(self, capsys):
        confirm_destructive.pre_tool("delete_file", {"path": "logs/old.log"})
        captured = capsys.readouterr()
        assert "Warning: Deleting file: logs/old.log" in captured.err


class TestEmbeddings:
    @pytest.mark.asyncio
    async def test_embedding_endpoint_returns_vector(self, async_client):
        """POST /api/embeddings returns embedding array when Ollama succeeds."""
        from unittest.mock import AsyncMock, MagicMock, patch

        vector = [0.1, 0.2, 0.3]

        # Create mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": vector}
        mock_response.raise_for_status = MagicMock()

        # Create mock client
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            payload = {"text": "hello world", "model": "custom-model"}
            result = await async_client.post("/api/embeddings", json=payload)

        assert result.status_code == 200
        data = result.json()
        assert data["success"] is True
        assert data["dimensions"] == len(vector)
        assert data["embedding"] == vector

    @pytest.mark.asyncio
    async def test_embedding_has_correct_dimensions(self, async_client):
        """nomic-embed-text returns 768 dimensions."""
        from unittest.mock import AsyncMock, MagicMock, patch

        vector = [0.0] * 768

        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": vector}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = await async_client.post("/api/embeddings", json={"text": "hello"})

        assert result.status_code == 200
        data = result.json()
        assert data["dimensions"] == 768
        assert data["embedding"] == vector
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_embedding_endpoint_handles_errors(self, async_client):
        """Invalid model returns error response."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid model"

        error = HTTPStatusError(
            "Bad request",
            request=MagicMock(),
            response=mock_response,
        )

        mock_client = AsyncMock()
        mock_client.post.side_effect = error
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            result = await async_client.post("/api/embeddings", json={"text": "oops", "model": "bad"})

        assert result.status_code == 200
        data = result.json()
        assert data["success"] is False
        assert "Ollama error 400" in data["error"]


class TestProjectMemory:
    def test_store_saves_to_database(self, fake_project_memory):
        memory = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")
        response = memory.store(
            content_type="doc",
            content="important note",
            file_path="notes/todo.md",
            summary="todo list",
            metadata={"source": "test"},
        )

        assert response["success"] is True
        assert response["id"] == 1
        record = fake_project_memory.records[0]
        assert record["content_type"] == "doc"
        assert record["file_path"] == "notes/todo.md"
        assert record["extra_data"] == {"source": "test"}

    def test_search_finds_stored_content(self, fake_project_memory):
        memory = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")
        memory.store(
            content_type="doc",
            content="Alpha content",
            summary="First summary",
            metadata={"phase": 1},
        )
        memory.store(
            content_type="solution",
            content="Beta code",
            summary="Second summary",
            metadata={"phase": 2},
        )

        result = memory.search("Alpha")

        assert result["success"] is True
        assert result["count"] == 1
        entry = result["results"][0]
        assert entry["content_type"] == "doc"
        assert "Alpha content" in entry["content"]
        assert entry["extra_data"] == {"phase": 1}

    def test_memory_persists_across_instances(self, fake_project_memory):
        memory_one = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")
        memory_one.store(
            content_type="doc",
            content="persisted content",
            summary="persist",
            metadata={"origin": "first"},
        )

        memory_two = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")
        result = memory_two.search("persisted")

        assert result["success"] is True
        assert result["count"] == 1
        assert result["results"][0]["summary"] == "persist"

    def test_get_context_formats_for_llm(self, fake_project_memory):
        memory = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")
        memory.store(
            content_type="doc",
            content="Contextual content",
            file_path="context/file.md",
            summary="context summary",
            metadata={"topic": "context"},
        )

        context = memory.get_context("Contextual")
        assert "### context/file.md" in context
        assert "Contextual content" in context


class TestAutoEmbed:
    """Tests for the auto_embed post-hook."""

    def test_auto_embed_skips_non_embeddable_tools(self):
        """auto_embed should skip tools not in EMBEDDABLE_TOOLS."""
        from forge.hooks import auto_embed

        result = {"success": True, "id": 1}
        auto_embed.post_tool("read_file", {"path": "/test.txt"}, result)

        # Should not have added embedding to result
        assert "embedding" not in result

    def test_auto_embed_skips_failed_results(self):
        """auto_embed should skip unsuccessful tool results."""
        from forge.hooks import auto_embed

        result = {"success": False, "error": "Failed"}
        auto_embed.post_tool("store_solution", {"content": "test content"}, result)

        assert "embedding" not in result

    def test_auto_embed_skips_trivial_content(self):
        """auto_embed should skip content shorter than 10 chars."""
        from forge.hooks import auto_embed

        result = {"success": True, "id": 1}
        auto_embed.post_tool("store_solution", {"content": "short"}, result)

        assert "embedding" not in result

    def test_auto_embed_calls_api_for_valid_content(self):
        """auto_embed should call embedding API for valid content."""
        from unittest.mock import patch, MagicMock
        from forge.hooks import auto_embed

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "embedding": [0.1] * 768}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        result = {"success": True, "id": 1}

        with patch("forge.hooks.auto_embed.httpx.Client", return_value=mock_client):
            auto_embed.post_tool(
                "store_solution",
                {"content": "This is a substantial piece of content to embed"},
                result,
            )

        assert "embedding" in result
        assert result["embedding_dimensions"] == 768

    def test_generate_embedding_sync_returns_vector(self):
        """generate_embedding_sync should return embedding vector."""
        from unittest.mock import patch, MagicMock
        from forge.hooks.auto_embed import generate_embedding_sync

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "embedding": [0.5] * 768}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("forge.hooks.auto_embed.httpx.Client", return_value=mock_client):
            embedding = generate_embedding_sync("test text")

        assert embedding is not None
        assert len(embedding) == 768

    def test_generate_embedding_sync_handles_timeout(self):
        """generate_embedding_sync should return None on timeout."""
        from unittest.mock import patch, MagicMock
        from forge.hooks.auto_embed import generate_embedding_sync
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)

        with patch("forge.hooks.auto_embed.httpx.Client", return_value=mock_client):
            embedding = generate_embedding_sync("test text")

        assert embedding is None


class TestContextInject:
    """Tests for the context_inject pre-hook."""

    def test_context_inject_skips_non_llm_tools(self):
        """context_inject should skip tools not in LLM_TOOLS."""
        from forge.hooks import b_context_inject as context_inject

        args = {"path": "/test.txt"}
        original_args = args.copy()

        result = context_inject.pre_tool("read_file", args)

        assert result is True  # Always proceeds
        assert args == original_args  # Args unchanged

    def test_context_inject_skips_empty_prompts(self):
        """context_inject should skip tools with no prompt."""
        from forge.hooks import b_context_inject as context_inject

        args = {"model": "test-model"}
        original_args = args.copy()

        result = context_inject.pre_tool("chat", args)

        assert result is True
        assert args == original_args

    def test_context_inject_modifies_prompt_when_context_found(self, monkeypatch):
        """context_inject should enhance prompt with context."""
        from forge.hooks import b_context_inject as context_inject

        # Mock _fetch_relevant_context to return test context
        monkeypatch.setattr(
            context_inject,
            "_fetch_relevant_context",
            lambda q: "### test.py\ndef hello(): pass",
        )

        args = {"prompt": "How do I use hello?"}

        result = context_inject.pre_tool("chat", args)

        assert result is True
        assert "## Relevant Context from Project Knowledge" in args["prompt"]
        assert "### test.py" in args["prompt"]
        assert "How do I use hello?" in args["prompt"]

    def test_context_inject_handles_message_key(self, monkeypatch):
        """context_inject should work with 'message' key."""
        from forge.hooks import b_context_inject as context_inject

        monkeypatch.setattr(
            context_inject,
            "_fetch_relevant_context",
            lambda q: "Context here",
        )

        args = {"message": "Original message"}

        context_inject.pre_tool("generate", args)

        assert "Context here" in args["message"]
        assert "Original message" in args["message"]

    def test_inject_context_public_api(self, monkeypatch):
        """inject_context should enhance prompts via public API."""
        from forge.hooks.b_context_inject import inject_context

        monkeypatch.setattr(
            "forge.hooks.b_context_inject._fetch_relevant_context",
            lambda q: "Relevant context",
        )

        enhanced = inject_context("My question")

        assert "Relevant context" in enhanced
        assert "My question" in enhanced

    def test_context_inject_returns_original_when_no_context(self, monkeypatch):
        """inject_context should return original prompt when no context found."""
        from forge.hooks.b_context_inject import inject_context

        monkeypatch.setattr(
            "forge.hooks.b_context_inject._fetch_relevant_context",
            lambda q: None,
        )

        result = inject_context("My question")

        assert result == "My question"


class TestPromptRefine:
    """Tests for the prompt_refine pre-hook."""

    def test_prompt_refine_skips_non_llm_tools(self):
        """prompt_refine should skip tools not in LLM_TOOLS."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"path": "/test.txt"}
        original_args = args.copy()

        result = prompt_refine.pre_tool("read_file", args)

        assert result is True  # Always proceeds
        assert args == original_args  # Args unchanged

    def test_prompt_refine_skips_empty_prompts(self):
        """prompt_refine should skip tools with very short prompts."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"prompt": "hi"}  # Too short (< 5 chars)
        original_prompt = args["prompt"]

        result = prompt_refine.pre_tool("chat", args)

        assert result is True
        assert args["prompt"] == original_prompt

    def test_prompt_refine_adds_code_gen_requirements(self):
        """prompt_refine should add requirements for code generation prompts."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"prompt": "Create a new authentication module"}

        prompt_refine.pre_tool("chat", args)

        assert "## Task" in args["prompt"]
        assert "## Requirements" in args["prompt"]
        assert "Create a new authentication module" in args["prompt"]
        assert "file location" in args["prompt"].lower()

    def test_prompt_refine_adds_bug_fix_requirements(self):
        """prompt_refine should add requirements for bug fix prompts."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"prompt": "Fix the login error in authentication"}

        prompt_refine.pre_tool("generate", args)

        assert "## Task" in args["prompt"]
        assert "## Requirements" in args["prompt"]
        assert "root cause" in args["prompt"].lower()

    def test_prompt_refine_adds_refactor_requirements(self):
        """prompt_refine should add requirements for refactor prompts."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"prompt": "Refactor the database connection handling"}

        prompt_refine.pre_tool("chat", args)

        assert "## Task" in args["prompt"]
        assert "behavior" in args["prompt"].lower()
        assert "minimal" in args["prompt"].lower()

    def test_prompt_refine_skips_questions(self):
        """prompt_refine should not modify question prompts."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"prompt": "What does this function do?"}
        original = args["prompt"]

        prompt_refine.pre_tool("chat", args)

        assert args["prompt"] == original

    def test_prompt_refine_stores_original(self):
        """prompt_refine should store original prompt for reference."""
        from forge.hooks import a_prompt_refine as prompt_refine

        args = {"prompt": "Add a new user registration feature"}

        prompt_refine.pre_tool("chat", args)

        assert "_original_prompt" in args
        assert args["_original_prompt"] == "Add a new user registration feature"

    def test_refine_prompt_includes_conventions(self):
        """refine_prompt should include project conventions."""
        from forge.hooks.a_prompt_refine import refine_prompt

        result = refine_prompt("Build a new API endpoint")

        assert "## Project Conventions" in result
        # Should have content after conventions header (from AGENTS.md or DEFAULT_CONVENTIONS)
        conv_section = result.split("## Project Conventions")[1]
        assert len(conv_section.strip()) > 10  # Has actual content

    def test_refine_prompt_with_custom_conventions(self):
        """refine_prompt should accept custom conventions."""
        from forge.hooks.a_prompt_refine import refine_prompt

        custom = "- Use TypeScript\n- Follow DRY principle"
        result = refine_prompt("Create a helper function", conventions=custom)

        assert "Use TypeScript" in result
        assert "DRY principle" in result


class TestHookChainOrder:
    """Tests for hook chain execution order."""

    def test_prompt_refine_runs_before_context_inject(self):
        """Verify a_prompt_refine runs before b_context_inject alphabetically."""
        from pathlib import Path
        import pkgutil

        hooks_dir = Path(__file__).parent.parent / "forge" / "hooks"
        hook_names = sorted([
            name for finder, name, _ispkg in pkgutil.iter_modules([str(hooks_dir)])
            if not name.startswith("_")
        ])

        # Verify alphabetical order puts prompt_refine before context_inject
        prompt_idx = next(i for i, n in enumerate(hook_names) if "prompt_refine" in n)
        context_idx = next(i for i, n in enumerate(hook_names) if "context_inject" in n)

        assert prompt_idx < context_idx, f"prompt_refine ({hook_names[prompt_idx]}) should run before context_inject ({hook_names[context_idx]})"

    def test_hook_chain_modifies_args_in_sequence(self, monkeypatch):
        """Verify hook chain processes args sequentially."""
        from forge.hooks import a_prompt_refine as prompt_refine
        from forge.hooks import b_context_inject as context_inject

        # Set up args for a code generation prompt
        args = {"prompt": "Create a new authentication module"}

        # Run prompt_refine first
        prompt_refine.pre_tool("chat", args)

        # Check refinements were added
        assert "## Task" in args["prompt"]
        assert "## Requirements" in args["prompt"]

        # Mock context fetch so context_inject adds context
        monkeypatch.setattr(
            context_inject,
            "_fetch_relevant_context",
            lambda q: "### auth.py\nclass AuthService: pass",
        )

        # Run context_inject on the refined prompt
        context_inject.pre_tool("chat", args)

        # Final prompt should have: context first, then refined task
        final_prompt = args["prompt"]
        context_pos = final_prompt.find("## Relevant Context")
        task_pos = final_prompt.find("## Task")

        assert context_pos >= 0, "Context section should be present"
        assert task_pos > context_pos, "Task section should come after context"
        assert "AuthService" in final_prompt, "Context content should be included"


class TestProjectMemoryPrune:
    """Tests for ProjectMemory prune functionality."""

    def test_prune_returns_success_structure(self, fake_project_memory, monkeypatch):
        """prune() should return success with pruned counts."""
        # Mock the prune methods to avoid actual DB operations
        memory = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")

        monkeypatch.setattr(memory, "_prune_stale", lambda x: 5)
        monkeypatch.setattr(memory, "_prune_excess", lambda x: 3)

        result = memory.prune(max_age_days=30, max_entries=100)

        assert result["success"] is True
        assert "pruned" in result
        assert result["pruned"]["stale"] == 5
        assert result["pruned"]["excess"] == 3
        assert result["total"] == 8

    def test_prune_handles_errors_gracefully(self, monkeypatch):
        """prune() should handle errors and return failure."""
        memory = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")

        def raise_error(x):
            raise Exception("DB Error")

        monkeypatch.setattr(memory, "_prune_stale", raise_error)

        result = memory.prune()

        assert result["success"] is False
        assert "error" in result

    def test_stats_returns_knowledge_base_info(self, fake_project_memory, monkeypatch):
        """stats() should return knowledge base statistics."""
        from unittest.mock import MagicMock

        memory = ProjectMemory(project_id=1, database_url="sqlite:///:memory:")

        # Mock the session for stats queries
        mock_session = MagicMock()
        mock_session.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=3)),  # total count
            MagicMock(fetchall=MagicMock(return_value=[("code", 2), ("doc", 1)])),  # by type
            MagicMock(fetchone=MagicMock(return_value=(None, None))),  # dates
        ]
        mock_session.close = MagicMock()

        monkeypatch.setattr(memory, "_get_session", lambda: mock_session)
        result = memory.stats()

        assert result["success"] is True
        assert result["stats"]["total"] == 3
        assert result["stats"]["by_type"] == {"code": 2, "doc": 1}
