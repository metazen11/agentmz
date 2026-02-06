"""Circuit breaker pattern to prevent cascading failures in subtask delegation."""
import time
from enum import Enum
from threading import Lock
from typing import Optional

from .constants import CIRCUIT_BREAKER_FAILURE_THRESHOLD, CIRCUIT_BREAKER_RESET_TIMEOUT


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation, requests flow through
    OPEN = "open"  # Failing, requests rejected immediately
    HALF_OPEN = "half_open"  # Testing if system recovered


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures in subtask delegation.

    Usage:
        breaker = CircuitBreaker()

        if not breaker.can_run():
            return {"error": "Circuit breaker open, too many failures"}

        try:
            result = run_subtask(...)
            breaker.record_success()
        except Exception as e:
            breaker.record_failure()
            raise
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        reset_timeout: int = CIRCUIT_BREAKER_RESET_TIMEOUT,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = Lock()

    def can_run(self) -> bool:
        """Check if a request can run."""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # Check if reset timeout has elapsed
                if self.last_failure_time is not None:
                    elapsed = time.time() - self.last_failure_time
                    if elapsed >= self.reset_timeout:
                        # Transition to half-open to test recovery
                        self.state = CircuitState.HALF_OPEN
                        return True
                return False

            # HALF_OPEN: allow one request through to test
            return True

    def record_success(self) -> None:
        """Record a successful execution."""
        with self._lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed execution."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Still failing, go back to open
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                # Too many failures, open the circuit
                self.state = CircuitState.OPEN

    def get_state(self) -> dict:
        """Get current circuit breaker state for diagnostics."""
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "last_failure_time": self.last_failure_time,
                "reset_timeout": self.reset_timeout,
            }

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None


# Global circuit breaker instance for subtask delegation
subtask_circuit_breaker = CircuitBreaker()
