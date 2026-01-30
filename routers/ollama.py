"""Router for Ollama service management.

Provides endpoints to:
- Check ollama status (container + API health)
- Restart ollama service (SSH → container fallback)
- Force specific restart methods
- Queue LLM requests (PostgreSQL-backed)
"""

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.ollama_service import get_ollama_service, OllamaStatus

# Lazy import queue service to avoid startup issues
_queue_service = None

def _get_queue_service():
    """Get queue service singleton, lazy init."""
    global _queue_service
    if _queue_service is None:
        try:
            from services.queue_service import queue_service
            _queue_service = queue_service
        except ImportError:
            return None
    return _queue_service

router = APIRouter(prefix="/ollama", tags=["ollama"])
logger = logging.getLogger(__name__)


class OllamaStatusResponse(BaseModel):
    """Response for GET /ollama/status."""
    container_status: str
    service_status: str
    models_loaded: List[str]
    error: Optional[str] = None


class RestartResponse(BaseModel):
    """Response for POST /ollama/restart endpoints."""
    success: bool
    method: str
    message: str
    duration_seconds: float


@router.get("/status", response_model=OllamaStatusResponse)
async def get_ollama_status():
    """Get current ollama service status.

    Returns:
        - container_status: running, stopped, or error
        - service_status: running, stopped, or error
        - models_loaded: list of loaded model names
        - error: error message if any
    """
    service = get_ollama_service()
    status = await service.get_status()
    return OllamaStatusResponse(
        container_status=status["container_status"],
        service_status=status["service_status"],
        models_loaded=status["models_loaded"],
        error=status.get("error"),
    )


@router.post("/restart", response_model=RestartResponse)
async def restart_ollama():
    """Restart the ollama service with fallback strategy.

    Attempts restart using cascading fallback:
    1. SSH restart (preferred - uses restart script inside container)
    2. Full container restart (slowest, most reliable)

    Returns:
        - success: whether restart succeeded
        - method: which method was used (ssh, container_restart)
        - message: details about the restart
        - duration_seconds: how long the restart took
    """
    service = get_ollama_service()

    logger.info("Initiating ollama restart with fallback...")
    result = await service.restart_with_fallback()

    if result.success:
        logger.info(f"Ollama restart successful via {result.method} in {result.duration_seconds:.2f}s")
    else:
        logger.error(f"Ollama restart failed: {result.message}")

    return RestartResponse(
        success=result.success,
        method=result.method,
        message=result.message,
        duration_seconds=result.duration_seconds,
    )


@router.post("/restart/ssh", response_model=RestartResponse)
async def restart_ollama_ssh():
    """Force restart via SSH.

    Requires SSH key to be configured and ollama container to have SSH server.
    Use this when you want to restart without killing the container.
    """
    service = get_ollama_service()

    logger.info("Initiating ollama restart via SSH...")
    result = await service.restart_via_ssh()

    return RestartResponse(
        success=result.success,
        method=result.method,
        message=result.message,
        duration_seconds=result.duration_seconds,
    )


@router.post("/restart/container", response_model=RestartResponse)
async def restart_ollama_container():
    """Force full container restart.

    Use this as a last resort when SSH restart fails or is not available.
    This will restart the entire Docker container.
    """
    service = get_ollama_service()

    logger.info("Initiating ollama container restart...")
    result = await service.restart_container()

    return RestartResponse(
        success=result.success,
        method=result.method,
        message=result.message,
        duration_seconds=result.duration_seconds,
    )


# ============================================================================
# Queue Endpoints - PostgreSQL-backed request queuing
# ============================================================================


class QueueGenerateRequest(BaseModel):
    """Request to enqueue a generate task."""
    model: str
    prompt: str
    options: Optional[dict] = None
    callback_url: Optional[str] = None


class QueueChatRequest(BaseModel):
    """Request to enqueue a chat task."""
    model: str
    messages: List[dict]
    options: Optional[dict] = None
    callback_url: Optional[str] = None


class QueueJobResponse(BaseModel):
    """Response after enqueuing a job."""
    job_id: int
    status: str = "queued"
    message: str


class QueueJobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: int
    status: str
    task_name: Optional[str] = None
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    attempts: Optional[int] = None


class QueueStatsResponse(BaseModel):
    """Response for queue statistics."""
    queue: str
    pending: int
    running: int
    completed: int
    failed: int


@router.post("/queue/generate", response_model=QueueJobResponse)
async def queue_generate(request: QueueGenerateRequest):
    """Enqueue an Ollama generate request.

    The request will be processed asynchronously by the queue worker.
    Use GET /ollama/queue/status/{job_id} to check status.

    Args:
        model: Ollama model name (e.g., "qwen3:0.6b")
        prompt: The prompt to send
        options: Optional Ollama options (temperature, etc.)
        callback_url: Optional URL to POST results when complete
    """
    queue_svc = _get_queue_service()
    if queue_svc is None:
        raise HTTPException(
            status_code=503,
            detail="Queue service not available (procrastinate not installed)"
        )

    base_url = os.environ.get("OLLAMA_URL", "http://wfhub-v2-ollama:11434")

    try:
        job_id = await queue_svc.enqueue_generate(
            model=request.model,
            prompt=request.prompt,
            base_url=base_url,
            options=request.options,
            callback_url=request.callback_url,
        )
        logger.info(f"Enqueued generate job {job_id} for model {request.model}")
        return QueueJobResponse(
            job_id=job_id,
            status="queued",
            message=f"Generate request queued with job_id={job_id}",
        )
    except Exception as e:
        logger.error(f"Failed to enqueue generate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/chat", response_model=QueueJobResponse)
async def queue_chat(request: QueueChatRequest):
    """Enqueue an Ollama chat request.

    The request will be processed asynchronously by the queue worker.
    Use GET /ollama/queue/status/{job_id} to check status.

    Args:
        model: Ollama model name
        messages: List of message dicts with 'role' and 'content'
        options: Optional Ollama options
        callback_url: Optional URL to POST results when complete
    """
    queue_svc = _get_queue_service()
    if queue_svc is None:
        raise HTTPException(
            status_code=503,
            detail="Queue service not available (procrastinate not installed)"
        )

    base_url = os.environ.get("OLLAMA_URL", "http://wfhub-v2-ollama:11434")

    try:
        job_id = await queue_svc.enqueue_chat(
            model=request.model,
            messages=request.messages,
            base_url=base_url,
            options=request.options,
            callback_url=request.callback_url,
        )
        logger.info(f"Enqueued chat job {job_id} for model {request.model}")
        return QueueJobResponse(
            job_id=job_id,
            status="queued",
            message=f"Chat request queued with job_id={job_id}",
        )
    except Exception as e:
        logger.error(f"Failed to enqueue chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/status/{job_id}", response_model=QueueJobStatusResponse)
async def get_queue_job_status(job_id: int):
    """Get status of a queued job.

    Args:
        job_id: The job ID returned from queue/generate or queue/chat

    Returns:
        Job status including: todo, doing, succeeded, failed
    """
    queue_svc = _get_queue_service()
    if queue_svc is None:
        raise HTTPException(
            status_code=503,
            detail="Queue service not available (procrastinate not installed)"
        )

    try:
        status = await queue_svc.get_job_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return QueueJobStatusResponse(
            job_id=status["job_id"],
            status=status["status"],
            task_name=status.get("task_name"),
            scheduled_at=status.get("scheduled_at"),
            started_at=status.get("started_at"),
            attempts=status.get("attempts"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats():
    """Get queue statistics.

    Returns counts of pending, running, completed, and failed jobs.
    """
    queue_svc = _get_queue_service()
    if queue_svc is None:
        raise HTTPException(
            status_code=503,
            detail="Queue service not available (procrastinate not installed)"
        )

    try:
        stats = await queue_svc.get_queue_stats()
        return QueueStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
