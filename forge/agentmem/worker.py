"""Background worker that processes pending observations.

Workflow:
1. Query observations where embedding IS NULL
2. For each observation:
   a. Load session history for context
   b. Classify (golden, gotcha, discovery, routine)
   c. If routine: DELETE
   d. Else: generate embedding, UPDATE
3. Repeat until no pending observations

Run modes:
- Single pass: process_pending()
- Continuous: run_worker()
- CLI: `forge mem process`
"""

import logging
import time
from typing import Optional

from forge.agentmem.classifier import classify_observation
from forge.agentmem.embedder import generate_embedding_for_observation, estimate_tokens
from forge.agentmem.models import Observation, ObservationType
from forge.agentmem.store import (
    get_pending_observations,
    get_session_observations,
    update_observation,
    delete_observation,
    count_pending,
)

logger = logging.getLogger(__name__)


def process_single(obs: Observation) -> tuple[str, ObservationType | None]:
    """Process a single observation.

    Returns:
        Tuple of (action, obs_type) where action is 'updated', 'deleted', or 'error'
    """
    try:
        # Load session history for context
        session_history = get_session_observations(obs.session_id)

        # Exclude current observation from history
        session_history = [h for h in session_history if h.id != obs.id]

        # Classify
        obs_type, title = classify_observation(obs, session_history)

        # If routine, delete
        if obs_type == ObservationType.ROUTINE:
            delete_observation(obs.id)
            logger.debug(f"Deleted routine observation {obs.id}: {title}")
            return "deleted", obs_type

        # Generate embedding
        embedding = generate_embedding_for_observation(
            tool=obs.tool,
            title=title,
            output_summary=obs.output_summary or "",
        )

        if embedding is None:
            logger.warning(f"Failed to generate embedding for observation {obs.id}")
            # Still update with classification but no embedding
            # Worker will retry on next pass

        # Estimate tokens
        content = f"{title}\n{obs.output_summary or ''}"
        tokens = estimate_tokens(content)

        # Update observation
        update_observation(
            obs_id=obs.id,
            obs_type=obs_type,
            title=title,
            tokens=tokens,
            embedding=embedding or [],
        )

        logger.debug(f"Updated observation {obs.id}: {obs_type.value} - {title}")
        return "updated", obs_type

    except Exception as e:
        logger.error(f"Error processing observation {obs.id}: {e}")
        return "error", None


def process_pending(limit: int = 100) -> dict[str, int]:
    """Process all pending observations (single pass).

    Args:
        limit: Maximum observations to process in one pass

    Returns:
        Dict with counts: {updated, deleted, errors, remaining}
    """
    stats = {"updated": 0, "deleted": 0, "errors": 0, "remaining": 0}

    pending = get_pending_observations(limit=limit)
    logger.info(f"Processing {len(pending)} pending observations")

    for obs in pending:
        action, obs_type = process_single(obs)
        if action == "updated":
            stats["updated"] += 1
        elif action == "deleted":
            stats["deleted"] += 1
        else:
            stats["errors"] += 1

    # Check remaining
    stats["remaining"] = count_pending()

    logger.info(
        f"Processed: {stats['updated']} updated, {stats['deleted']} deleted, "
        f"{stats['errors']} errors, {stats['remaining']} remaining"
    )

    return stats


def run_worker(
    interval_seconds: int = 10,
    max_iterations: Optional[int] = None,
) -> None:
    """Run worker continuously, processing pending observations.

    Args:
        interval_seconds: Sleep time between processing passes
        max_iterations: Stop after N iterations (None = run forever)
    """
    iteration = 0
    logger.info(f"Starting worker (interval={interval_seconds}s)")

    try:
        while True:
            iteration += 1

            pending_count = count_pending()
            if pending_count > 0:
                logger.info(f"Iteration {iteration}: {pending_count} pending")
                process_pending()
            else:
                logger.debug(f"Iteration {iteration}: No pending observations")

            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations})")
                break

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logger.info("Worker stopped by user")


if __name__ == "__main__":
    # Run worker when executed directly
    logging.basicConfig(level=logging.INFO)
    run_worker()
