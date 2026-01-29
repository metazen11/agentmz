"""Safety constants for subtask delegation system."""

# Maximum depth of nested subtask delegation
# Prevents infinite recursion: parent -> child -> grandchild (depth 3 max)
MAX_DELEGATION_DEPTH = 3

# Maximum number of subtasks a single task can create
# Prevents runaway task creation
MAX_SUBTASKS_PER_TASK = 10

# Maximum time to wait for a subtask to complete (seconds)
SUBTASK_TIMEOUT_SECONDS = 300

# Maximum iterations per agent run
MAX_ITERATIONS = 20

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3  # Open after 3 consecutive failures
CIRCUIT_BREAKER_RESET_TIMEOUT = 60  # Reset after 60 seconds
