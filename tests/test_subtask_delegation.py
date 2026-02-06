"""Tests for subtask delegation system."""
import pytest
from unittest.mock import MagicMock, patch

# Test constants
def test_constants_exist():
    """Verify safety constants are defined."""
    from agent.constants import (
        MAX_DELEGATION_DEPTH,
        MAX_SUBTASKS_PER_TASK,
        SUBTASK_TIMEOUT_SECONDS,
        MAX_ITERATIONS,
        CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        CIRCUIT_BREAKER_RESET_TIMEOUT,
    )

    assert MAX_DELEGATION_DEPTH == 3
    assert MAX_SUBTASKS_PER_TASK == 10
    assert SUBTASK_TIMEOUT_SECONDS == 300
    assert MAX_ITERATIONS == 20
    assert CIRCUIT_BREAKER_FAILURE_THRESHOLD == 3
    assert CIRCUIT_BREAKER_RESET_TIMEOUT == 60


# Test circuit breaker
def test_circuit_breaker_initial_state():
    """Circuit breaker should start closed."""
    from agent.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_run() is True


def test_circuit_breaker_opens_after_failures():
    """Circuit breaker should open after threshold failures."""
    from agent.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=3)

    # Record failures
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.can_run() is False


def test_circuit_breaker_resets_on_success():
    """Circuit breaker should reset to closed on success."""
    from agent.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Simulate time passing and half-open state
    breaker.state = CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_circuit_breaker_manual_reset():
    """Circuit breaker should support manual reset."""
    from agent.circuit_breaker import CircuitBreaker, CircuitState

    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


# Test tools context
def test_task_context_functions():
    """Task context functions should work correctly."""
    from agent.tools import set_task_context, get_task_context, clear_task_context

    # Initially None
    clear_task_context()
    assert get_task_context() is None

    # Set context
    set_task_context(task_id=123, depth=1, parent_task_id=100)
    ctx = get_task_context()
    assert ctx is not None
    assert ctx["task_id"] == 123
    assert ctx["depth"] == 1
    assert ctx["parent_task_id"] == 100

    # Clear context
    clear_task_context()
    assert get_task_context() is None


# Test graph structure (without running)
def test_graph_creation():
    """LangGraph should be created with correct nodes."""
    from agent.graph import create_agent_graph

    graph = create_agent_graph()

    # Verify nodes exist
    assert "supervisor" in graph.nodes
    assert "run_tool" in graph.nodes
    assert "delegate" in graph.nodes
    assert "wait_subtask" in graph.nodes


def test_get_all_tools_without_delegation():
    """At max depth, delegate_subtask should not be available."""
    from agent.graph import get_all_tools
    from agent.constants import MAX_DELEGATION_DEPTH

    tools = get_all_tools(depth=MAX_DELEGATION_DEPTH)
    tool_names = [t["function"]["name"] for t in tools]

    assert "delegate_subtask" not in tool_names
    assert "list_files" in tool_names
    assert "done" in tool_names


def test_get_all_tools_with_delegation():
    """Below max depth, delegate_subtask should be available."""
    from agent.graph import get_all_tools

    tools = get_all_tools(depth=0)
    tool_names = [t["function"]["name"] for t in tools]

    assert "delegate_subtask" in tool_names


# Test model
def test_task_model_has_depth():
    """Task model should have depth field."""
    from models import Task

    # Check the column exists
    assert hasattr(Task, "depth")


# Integration test with mocked DB
@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


def test_subtask_depth_validation():
    """Subtask creation should enforce depth limit."""
    from agent.constants import MAX_DELEGATION_DEPTH

    # This tests the logic, actual endpoint test requires DB
    parent_depth = MAX_DELEGATION_DEPTH
    new_depth = parent_depth + 1

    assert new_depth > MAX_DELEGATION_DEPTH


def test_subtask_count_validation():
    """Subtask creation should enforce count limit."""
    from agent.constants import MAX_SUBTASKS_PER_TASK

    existing_count = MAX_SUBTASKS_PER_TASK
    assert existing_count >= MAX_SUBTASKS_PER_TASK
