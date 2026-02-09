"""Tests for agent memory system.

Tests cover:
- Observation models and dataclasses
- Classification logic
- Store operations (mocked DB)
- Retrieval (mocked embeddings)
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from forge.agentmem.models import Observation, ObservationType
from forge.agentmem.classifier import classify_observation, _hash_observation


class TestObservationModel:
    """Tests for Observation dataclass."""

    def test_create_observation(self):
        """Test basic observation creation."""
        obs = Observation(
            session_id="test-session-123",
            tool="bash",
            success=True,
            args_summary="cmd='pytest'",
            output_summary="3 tests passed",
        )

        assert obs.session_id == "test-session-123"
        assert obs.tool == "bash"
        assert obs.success is True
        assert obs.embedding is None  # NULL until processed

    def test_observation_fields(self):
        """Test observation fields."""
        obs = Observation(
            session_id="test-session",
            tool="read",
            success=True,
            exit_code=0,
            duration_ms=50,
            project_id=1,
            file_path="/path/to/file.py",
        )

        assert obs.session_id == "test-session"
        assert obs.tool == "read"
        assert obs.success is True
        assert obs.exit_code == 0
        assert obs.project_id == 1
        assert obs.embedding is None


class TestClassifier:
    """Tests for rule-based observation classifier."""

    def test_classify_routine_repeated_success(self):
        """Repeated identical successes should be classified as routine."""
        obs = Observation(
            session_id="sess1",
            tool="read",
            success=True,
            args_summary="file='/path/to/file.py'",
        )
        obs.id = 10

        # History with identical successful calls
        history = [
            Observation(
                id=1,
                session_id="sess1",
                tool="read",
                success=True,
                args_summary="file='/path/to/file.py'",
            ),
            Observation(
                id=2,
                session_id="sess1",
                tool="read",
                success=True,
                args_summary="file='/path/to/file.py'",
            ),
        ]

        obs_type, title = classify_observation(obs, history)

        assert obs_type == ObservationType.ROUTINE

    def test_classify_gotcha_on_failure(self):
        """Failed tool calls should be classified as gotcha."""
        obs = Observation(
            session_id="sess1",
            tool="bash",
            success=False,
            exit_code=1,
            output_summary="Error: command not found",
        )
        obs.id = 1

        obs_type, title = classify_observation(obs, [])

        assert obs_type == ObservationType.GOTCHA
        assert "error" in title.lower() or "failed" in title.lower()

    def test_classify_golden_after_failures(self):
        """Success after failures should be classified as golden."""
        obs = Observation(
            id=3,
            session_id="sess1",
            tool="pytest",
            success=True,
            output_summary="All tests passed",
        )

        # History with previous failures
        history = [
            Observation(
                id=1,
                session_id="sess1",
                tool="pytest",
                success=False,
                output_summary="2 tests failed",
            ),
            Observation(
                id=2,
                session_id="sess1",
                tool="pytest",
                success=False,
                output_summary="1 test failed",
            ),
        ]

        obs_type, title = classify_observation(obs, history)

        assert obs_type == ObservationType.GOLDEN
        assert "3 attempts" in title

    def test_classify_discovery_first_use(self):
        """First use of a tool should be classified as discovery."""
        obs = Observation(
            id=1,
            session_id="sess1",
            tool="docker",
            success=True,
            args_summary="cmd='docker ps'",
        )

        # Empty history - first use
        obs_type, title = classify_observation(obs, [])

        assert obs_type == ObservationType.DISCOVERY
        assert "first" in title.lower() or "docker" in title.lower()

    def test_hash_observation_consistency(self):
        """Same tool+args should produce same hash."""
        obs1 = Observation(
            session_id="s1",
            tool="bash",
            success=True,
            args_summary="cmd='ls -la'",
        )
        obs2 = Observation(
            session_id="s2",  # Different session
            tool="bash",
            success=False,  # Different success
            args_summary="cmd='ls -la'",  # Same args
        )

        assert _hash_observation(obs1) == _hash_observation(obs2)


class TestEmbedder:
    """Tests for embedding generation."""

    @patch("forge.agentmem.embedder.httpx.Client")
    def test_generate_embedding_success(self, mock_client_class):
        """Test successful embedding generation."""
        from forge.agentmem.embedder import generate_embedding

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "embedding": [0.1] * 768
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = generate_embedding("test text")

        assert result is not None
        assert len(result) == 768

    @patch("forge.agentmem.embedder.httpx.Client")
    def test_generate_embedding_empty_text(self, mock_client_class):
        """Empty text should return None."""
        from forge.agentmem.embedder import generate_embedding

        result = generate_embedding("")

        assert result is None
        mock_client_class.assert_not_called()


class TestStore:
    """Tests for database store operations."""

    def test_observation_dataclass(self):
        """Test observation dataclass creation without DB."""
        obs = Observation(
            session_id="test-sess",
            tool="bash",
            success=True,
            args_summary="cmd='ls'",
            output_summary="file1.py file2.py",
        )

        assert obs.session_id == "test-sess"
        assert obs.tool == "bash"
        assert obs.success is True
        assert obs.args_summary == "cmd='ls'"


class TestRetrieval:
    """Tests for retrieval and search."""

    def test_format_hints_for_prompt(self):
        """Test formatting hints for prompt injection."""
        from forge.agentmem.retrieval import format_hints_for_prompt

        hints = [
            {
                "obs_type": "golden",
                "title": "pytest: Fixed import error",
                "output_summary": "Added __init__.py",
            },
            {
                "obs_type": "gotcha",
                "title": "bash: Permission denied",
                "output_summary": "Need sudo",
            },
        ]

        result = format_hints_for_prompt(hints)

        assert "Previous Similar Issues" in result
        assert "Fix" in result  # golden type
        assert "Issue" in result  # gotcha type
        assert "pytest" in result
        assert "Permission denied" in result

    def test_format_hints_empty(self):
        """Empty hints should return empty string."""
        from forge.agentmem.retrieval import format_hints_for_prompt

        result = format_hints_for_prompt([])

        assert result == ""


class TestContextInjection:
    """Tests for context injection hook."""

    def test_is_failure_detection(self):
        """Test failure detection from results."""
        from forge.hooks.b_context_inject import _is_failure

        # Explicit failure
        assert _is_failure({"success": False}) is True

        # Exit code failure
        assert _is_failure({"exit_code": 1}) is True

        # Error message
        assert _is_failure({"error": "Something went wrong"}) is True

        # Success cases
        assert _is_failure({"success": True}) is False
        assert _is_failure({"exit_code": 0}) is False
        assert _is_failure(None) is False

    def test_extract_error_output(self):
        """Test error output extraction."""
        from forge.hooks.b_context_inject import _extract_error_output

        # Error field
        result = _extract_error_output({"error": "Connection refused"})
        assert result == "Connection refused"

        # Output field
        result = _extract_error_output({"output": "Command failed"})
        assert result == "Command failed"

        # Long output truncation
        long_output = "x" * 1000
        result = _extract_error_output({"output": long_output})
        assert len(result) <= 500
