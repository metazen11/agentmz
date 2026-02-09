"""Rule-based observation classifier.

Classifies observations into:
- GOLDEN: Hard-won success (multiple attempts, or complex solution)
- GOTCHA: Error that taught something (failure followed by insight)
- DISCOVERY: First use of tool/pattern in session
- ROUTINE: Repeated identical success (will be deleted)

No LLM required - uses deterministic rules based on session context.
"""

import hashlib
import logging
import re
from typing import List, Optional

from forge.agentmem.models import Observation, ObservationType

logger = logging.getLogger(__name__)

# Tools that are typically routine (file reads, status checks)
ROUTINE_TOOLS = {"read", "glob", "grep", "ls", "cat", "pwd", "which", "echo"}

# Error patterns that indicate learning
ERROR_PATTERNS = [
    r"error",
    r"failed",
    r"exception",
    r"traceback",
    r"not found",
    r"permission denied",
    r"timeout",
    r"connection refused",
    r"syntax error",
    r"import error",
    r"module not found",
]

# Success patterns that indicate hard work
EFFORT_PATTERNS = [
    r"fixed",
    r"solved",
    r"works now",
    r"successfully",
    r"passed",
    r"tests pass",
    r"build succeeded",
]


def _hash_observation(obs: Observation) -> str:
    """Create hash of tool + args for deduplication."""
    content = f"{obs.tool}:{obs.args_summary}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def _is_error_output(output: str) -> bool:
    """Check if output indicates an error."""
    if not output:
        return False
    output_lower = output.lower()
    return any(re.search(pattern, output_lower) for pattern in ERROR_PATTERNS)


def _is_effort_output(output: str) -> bool:
    """Check if output indicates effort/resolution."""
    if not output:
        return False
    output_lower = output.lower()
    return any(re.search(pattern, output_lower) for pattern in EFFORT_PATTERNS)


def classify_observation(
    obs: Observation,
    session_history: List[Observation],
) -> tuple[ObservationType, str]:
    """Classify an observation based on session context.

    Args:
        obs: The observation to classify
        session_history: Previous observations in the same session

    Returns:
        Tuple of (ObservationType, title)
    """
    tool = obs.tool.lower()
    output = obs.output_summary or ""

    # === ROUTINE: Repeated identical success ===
    if obs.success:
        obs_hash = _hash_observation(obs)
        same_tool_successes = [
            h for h in session_history
            if h.tool == obs.tool
            and h.success
            and _hash_observation(h) == obs_hash
            and h.id != obs.id
        ]
        if len(same_tool_successes) >= 2:
            return ObservationType.ROUTINE, f"Routine {obs.tool} call"

    # === ROUTINE: Common read-only tools with success ===
    if obs.success and tool in ROUTINE_TOOLS:
        # Unless it's the first use or has interesting output
        first_use = not any(h.tool == obs.tool for h in session_history if h.id != obs.id)
        if not first_use and not _is_effort_output(output):
            return ObservationType.ROUTINE, f"Routine {obs.tool} call"

    # === GOTCHA: Failed with error message ===
    if not obs.success or _is_error_output(output):
        # Check if this is part of a problem-solution sequence
        # (error followed by success on same tool)
        title = _generate_error_title(obs)
        return ObservationType.GOTCHA, title

    # === GOLDEN: Success after multiple attempts ===
    failed_attempts = [
        h for h in session_history
        if h.tool == obs.tool
        and not h.success
        and h.id != obs.id
    ]
    if obs.success and len(failed_attempts) >= 1:
        title = _generate_golden_title(obs, failed_attempts)
        return ObservationType.GOLDEN, title

    # === DISCOVERY: First use of tool in session ===
    first_use = not any(h.tool == obs.tool for h in session_history if h.id != obs.id)
    if first_use:
        title = _generate_discovery_title(obs)
        return ObservationType.DISCOVERY, title

    # === GOLDEN: Success with effort indicators ===
    if obs.success and _is_effort_output(output):
        title = _generate_effort_title(obs)
        return ObservationType.GOLDEN, title

    # Default to discovery for anything else interesting
    return ObservationType.DISCOVERY, _generate_generic_title(obs)


def _generate_error_title(obs: Observation) -> str:
    """Generate title for error observation."""
    output = obs.output_summary or ""

    # Try to extract specific error type
    for pattern in ERROR_PATTERNS:
        if match := re.search(f"({pattern}[^.\\n]{{0,50}})", output.lower()):
            error_snippet = match.group(1).strip()
            return f"{obs.tool}: {error_snippet[:50]}"

    # Fallback
    if obs.exit_code and obs.exit_code != 0:
        return f"{obs.tool} failed (exit {obs.exit_code})"
    return f"{obs.tool} error encountered"


def _generate_golden_title(obs: Observation, failed_attempts: List[Observation]) -> str:
    """Generate title for hard-won success."""
    attempts = len(failed_attempts) + 1
    return f"{obs.tool}: Succeeded after {attempts} attempts"


def _generate_discovery_title(obs: Observation) -> str:
    """Generate title for first-use discovery."""
    args = obs.args_summary or ""
    # Extract key info from args
    if "file" in args.lower() or "path" in args.lower():
        # Try to extract filename
        if match := re.search(r'["\']([^"\']+)["\']', args):
            filename = match.group(1).split("/")[-1][:30]
            return f"First {obs.tool}: {filename}"
    return f"First use of {obs.tool}"


def _generate_effort_title(obs: Observation) -> str:
    """Generate title for success with effort indicators."""
    output = obs.output_summary or ""
    for pattern in EFFORT_PATTERNS:
        if match := re.search(f"({pattern}[^.\\n]{{0,30}})", output.lower()):
            snippet = match.group(1).strip()
            return f"{obs.tool}: {snippet}"
    return f"{obs.tool}: Completed successfully"


def _generate_generic_title(obs: Observation) -> str:
    """Generate generic title for observation."""
    if obs.success:
        return f"{obs.tool}: Completed"
    return f"{obs.tool}: Attempted"
