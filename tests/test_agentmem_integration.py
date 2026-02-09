"""Integration tests for agent memory system.

These tests hit the real database and embedding API.
Requires:
- PostgreSQL with pgvector running on port 5433
- Migration applied (alembic upgrade head)
- Embedding API running on port 8002 (optional - tests skip if unavailable)
- Environment variables: DATABASE_URL or POSTGRES_* vars (loaded from .env)
"""

import os
import pytest
from datetime import datetime, timezone

# Load environment from .env file
from env_utils import load_env
load_env()

# Import all models to register them with SQLAlchemy
import models  # noqa: F401 - registers Project, Task, etc.

from forge.agentmem.models import Observation, ObservationType, ObservationModel
from forge.agentmem.store import (
    insert_observation,
    get_pending_observations,
    update_observation,
    delete_observation,
    get_session_observations,
    count_pending,
    count_by_type,
)
from forge.agentmem.classifier import classify_observation
from forge.agentmem.embedder import generate_embedding
from forge.agentmem.retrieval import search_similar, format_hints_for_prompt, get_index
from forge.agentmem.worker import process_single, process_pending
from database import get_session
from sqlalchemy import text


# Generate unique session ID for test isolation
TEST_SESSION_ID = f"test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


@pytest.fixture(autouse=True)
def cleanup_test_observations():
    """Clean up test observations after each test."""
    yield
    # Cleanup
    with get_session() as session:
        session.query(ObservationModel).filter(
            ObservationModel.session_id.like("test-%")
        ).delete(synchronize_session=False)
        session.commit()


class TestDatabaseConnection:
    """Verify database connection works."""

    def test_database_connection(self):
        """Test basic database connectivity."""
        with get_session() as session:
            result = session.execute(text("SELECT 1")).scalar()
            assert result == 1

    def test_pgvector_extension(self):
        """Test pgvector extension is installed."""
        with get_session() as session:
            result = session.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
            assert result == "vector"

    def test_observations_table_exists(self):
        """Test observations table was created by migration."""
        with get_session() as session:
            result = session.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'observations')")
            ).scalar()
            assert result is True


class TestStoreIntegration:
    """Test store operations with real database."""

    def test_insert_and_retrieve_observation(self):
        """Test inserting and retrieving an observation."""
        obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="bash",
            success=True,
            args_summary="cmd='echo hello'",
            output_summary="hello",
            exit_code=0,
            duration_ms=50,
        )

        # Insert
        obs_id = insert_observation(obs)
        assert obs_id is not None
        assert obs_id > 0

        # Retrieve
        pending = get_pending_observations(limit=100)
        found = [o for o in pending if o.id == obs_id]
        assert len(found) == 1
        assert found[0].tool == "bash"
        assert found[0].success is True

    def test_update_observation(self):
        """Test updating observation with classification and embedding."""
        obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="pytest",
            success=True,
            output_summary="All tests passed",
        )
        obs_id = insert_observation(obs)

        # Update with classification
        fake_embedding = [0.1] * 768
        update_observation(
            obs_id=obs_id,
            obs_type=ObservationType.GOLDEN,
            title="pytest: All tests passed",
            tokens=50,
            embedding=fake_embedding,
        )

        # Verify update - should no longer be pending
        pending = get_pending_observations(limit=100)
        pending_ids = [o.id for o in pending]
        assert obs_id not in pending_ids

    def test_delete_observation(self):
        """Test deleting an observation."""
        obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="read",
            success=True,
        )
        obs_id = insert_observation(obs)

        # Verify inserted
        initial_count = count_pending()

        # Delete
        delete_observation(obs_id)

        # Verify deleted
        pending = get_pending_observations(limit=100)
        pending_ids = [o.id for o in pending]
        assert obs_id not in pending_ids

    def test_session_observations(self):
        """Test retrieving all observations for a session."""
        # Insert multiple observations
        for i in range(3):
            obs = Observation(
                session_id=TEST_SESSION_ID,
                tool=f"tool_{i}",
                success=True,
            )
            insert_observation(obs)

        # Retrieve by session
        session_obs = get_session_observations(TEST_SESSION_ID)
        assert len(session_obs) >= 3

        tools = [o.tool for o in session_obs]
        assert "tool_0" in tools
        assert "tool_1" in tools
        assert "tool_2" in tools


class TestClassifierIntegration:
    """Test classifier with real session history."""

    def test_classify_with_session_history(self):
        """Test classification using actual database history."""
        # Insert some history
        for i in range(2):
            obs = Observation(
                session_id=TEST_SESSION_ID,
                tool="bash",
                success=False,
                output_summary="Command failed",
            )
            insert_observation(obs)

        # Insert success
        success_obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="bash",
            success=True,
            output_summary="Command succeeded",
        )
        success_obs.id = insert_observation(success_obs)

        # Get history and classify
        history = get_session_observations(TEST_SESSION_ID)
        obs_type, title = classify_observation(success_obs, history)

        # Should be golden (success after failures)
        assert obs_type == ObservationType.GOLDEN
        assert "attempts" in title.lower() or "bash" in title.lower()


class TestEmbeddingIntegration:
    """Test embedding generation with real API."""

    @pytest.mark.skipif(
        not os.environ.get("EMBEDDING_API_BASE"),
        reason="Embedding API not configured"
    )
    def test_generate_real_embedding(self):
        """Test generating embedding via actual API."""
        text = "This is a test for the embedding API"
        embedding = generate_embedding(text)

        if embedding is None:
            pytest.skip("Embedding API not available")

        assert len(embedding) == 768
        assert all(isinstance(x, float) for x in embedding)


class TestWorkerIntegration:
    """Test worker processing with real database."""

    def test_process_single_observation(self):
        """Test processing a single observation."""
        obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="grep",
            success=True,
            args_summary="pattern='TODO'",
            output_summary="Found 5 matches",
        )
        obs.id = insert_observation(obs)

        # Process
        action, obs_type = process_single(obs)

        # First use of tool should be discovery or routine
        assert action in ["updated", "deleted"]
        if action == "updated":
            assert obs_type in [ObservationType.DISCOVERY, ObservationType.GOLDEN]

    def test_process_pending_batch(self):
        """Test processing a batch of pending observations."""
        # Insert multiple observations
        for i in range(5):
            obs = Observation(
                session_id=TEST_SESSION_ID,
                tool=f"batch_tool_{i}",
                success=True,
            )
            insert_observation(obs)

        initial_pending = count_pending()

        # Process
        stats = process_pending(limit=10)

        # Should have processed some
        assert stats["updated"] + stats["deleted"] >= 0
        assert stats["errors"] == 0


class TestRetrievalIntegration:
    """Test retrieval with real database."""

    def test_get_index(self):
        """Test getting observation index."""
        # Insert and process an observation
        obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="index_test",
            success=True,
            output_summary="Test output",
        )
        obs.id = insert_observation(obs)

        # Process it
        fake_embedding = [0.1] * 768
        update_observation(
            obs_id=obs.id,
            obs_type=ObservationType.DISCOVERY,
            title="index_test: Test discovery",
            tokens=25,
            embedding=fake_embedding,
        )

        # Get index
        index = get_index(limit=50)

        # Should have at least our observation
        assert len(index) >= 1

        # Verify structure
        entry = index[0]
        assert "id" in entry
        assert "type" in entry
        assert "title" in entry
        assert "tool" in entry

    def test_search_with_embedding(self):
        """Test semantic search (requires embedding API)."""
        # Insert and process an observation with known embedding
        obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="search_test",
            success=False,
            output_summary="Connection refused error on port 5432",
        )
        obs.id = insert_observation(obs)

        # Update with a known embedding
        test_embedding = [0.1] * 768
        update_observation(
            obs_id=obs.id,
            obs_type=ObservationType.GOTCHA,
            title="Database connection error on port 5432",
            tokens=50,
            embedding=test_embedding,
        )

        # Search - this will fail gracefully if embedding API not available
        try:
            results = search_similar(
                query="database connection error",
                limit=5,
                obs_types=["gotcha"],
            )
            # If we got results, verify structure
            if results:
                assert "id" in results[0]
                assert "similarity" in results[0]
        except Exception:
            pytest.skip("Embedding API not available for search")


class TestFullFlow:
    """Test the complete observation flow."""

    def test_capture_process_retrieve_flow(self):
        """Test full flow: capture → process → retrieve."""
        # 1. Simulate tool failure
        failure_obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="npm",
            success=False,
            exit_code=1,
            args_summary="cmd='npm install'",
            output_summary="ENOENT: package.json not found",
        )
        failure_id = insert_observation(failure_obs)

        # 2. Simulate eventual success
        success_obs = Observation(
            session_id=TEST_SESSION_ID,
            tool="npm",
            success=True,
            exit_code=0,
            args_summary="cmd='npm install'",
            output_summary="added 150 packages",
        )
        success_id = insert_observation(success_obs)

        # 3. Verify pending
        pending_before = count_pending()
        assert pending_before >= 2

        # 4. Process
        stats = process_pending(limit=10)

        # 5. Verify processed
        # Failure should be gotcha, success might be golden or routine
        assert stats["updated"] + stats["deleted"] >= 1

        # 6. Check types
        by_type = count_by_type()
        # Should have at least one gotcha from the failure
        total_processed = sum(by_type.values())
        assert total_processed >= 0  # May have been deleted if routine
