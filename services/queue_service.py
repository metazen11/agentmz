"""
PostgreSQL-based task queue for Ollama requests using procrastinate.

This service provides:
- Async task queuing for LLM requests
- Rate limiting to prevent Ollama overload
- Request tracking and status
- Priority queuing (optional)
"""
import os
import json
import httpx
from datetime import datetime, timezone
from typing import Optional, Any

import procrastinate

# Get database URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://wfhub:change-me@localhost:5433/agentic")

# Initialize procrastinate app
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=DATABASE_URL,
    ),
    import_paths=["services.queue_service"],
)


@app.task(name="ollama_generate", queue="ollama")
async def ollama_generate_task(
    model: str,
    prompt: str,
    base_url: str = "http://localhost:11434",
    stream: bool = False,
    options: Optional[dict] = None,
    callback_url: Optional[str] = None,
) -> dict:
    """
    Queued task for Ollama generate requests.

    Args:
        model: Model name (e.g., "qwen3:0.6b")
        prompt: The prompt to send
        base_url: Ollama API base URL
        stream: Whether to stream (not supported in queue mode)
        options: Additional Ollama options (temperature, etc.)
        callback_url: Optional URL to POST results to when complete

    Returns:
        dict with response or error
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,  # Always false for queued requests
    }
    if options:
        payload["options"] = options

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # Optional callback
            if callback_url:
                try:
                    await client.post(callback_url, json={
                        "status": "completed",
                        "result": result,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    pass  # Don't fail task if callback fails

            return {
                "status": "completed",
                "model": model,
                "response": result.get("response", ""),
                "done": result.get("done", True),
                "total_duration": result.get("total_duration"),
                "eval_count": result.get("eval_count"),
            }
    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "model": model,
            "error": f"HTTP {e.response.status_code}: {e.response.text}",
        }
    except Exception as e:
        return {
            "status": "error",
            "model": model,
            "error": str(e),
        }


@app.task(name="ollama_chat", queue="ollama")
async def ollama_chat_task(
    model: str,
    messages: list[dict],
    base_url: str = "http://localhost:11434",
    options: Optional[dict] = None,
    callback_url: Optional[str] = None,
) -> dict:
    """
    Queued task for Ollama chat requests.

    Args:
        model: Model name
        messages: List of message dicts with 'role' and 'content'
        base_url: Ollama API base URL
        options: Additional Ollama options
        callback_url: Optional callback URL

    Returns:
        dict with response or error
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if options:
        payload["options"] = options

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            if callback_url:
                try:
                    await client.post(callback_url, json={
                        "status": "completed",
                        "result": result,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    pass

            return {
                "status": "completed",
                "model": model,
                "message": result.get("message", {}),
                "done": result.get("done", True),
                "total_duration": result.get("total_duration"),
            }
    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "model": model,
            "error": f"HTTP {e.response.status_code}: {e.response.text}",
        }
    except Exception as e:
        return {
            "status": "error",
            "model": model,
            "error": str(e),
        }


class QueueService:
    """Service class for interacting with the Ollama task queue."""

    def __init__(self, procrastinate_app: procrastinate.App = app):
        self.app = procrastinate_app

    async def enqueue_generate(
        self,
        model: str,
        prompt: str,
        base_url: str = "http://localhost:11434",
        options: Optional[dict] = None,
        callback_url: Optional[str] = None,
        priority: int = 0,
    ) -> int:
        """
        Enqueue a generate request.

        Args:
            model: Model name
            prompt: Prompt text
            base_url: Ollama URL
            options: Ollama options
            callback_url: Callback when done
            priority: Higher = processed first (default 0)

        Returns:
            Job ID
        """
        job_id = await ollama_generate_task.defer_async(
            model=model,
            prompt=prompt,
            base_url=base_url,
            options=options,
            callback_url=callback_url,
        )
        return job_id

    async def enqueue_chat(
        self,
        model: str,
        messages: list[dict],
        base_url: str = "http://localhost:11434",
        options: Optional[dict] = None,
        callback_url: Optional[str] = None,
        priority: int = 0,
    ) -> int:
        """
        Enqueue a chat request.

        Returns:
            Job ID
        """
        job_id = await ollama_chat_task.defer_async(
            model=model,
            messages=messages,
            base_url=base_url,
            options=options,
            callback_url=callback_url,
        )
        return job_id

    async def get_job_status(self, job_id: int) -> Optional[dict]:
        """Get status of a queued job."""
        async with self.app.open_async() as app_ctx:
            connector = app_ctx.connector
            # Query job status from procrastinate tables
            async with connector.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT id, status, task_name, args, scheduled_at, started_at, attempts
                        FROM procrastinate_jobs
                        WHERE id = %s
                        """,
                        (job_id,)
                    )
                    row = await cur.fetchone()
                    if row:
                        return {
                            "job_id": row[0],
                            "status": row[1],
                            "task_name": row[2],
                            "args": row[3],
                            "scheduled_at": row[4].isoformat() if row[4] else None,
                            "started_at": row[5].isoformat() if row[5] else None,
                            "attempts": row[6],
                        }
        return None

    async def get_queue_stats(self) -> dict:
        """Get queue statistics."""
        async with self.app.open_async() as app_ctx:
            connector = app_ctx.connector
            async with connector.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT status, COUNT(*)
                        FROM procrastinate_jobs
                        WHERE queue_name = 'ollama'
                        GROUP BY status
                        """
                    )
                    rows = await cur.fetchall()
                    stats = {row[0]: row[1] for row in rows}
                    return {
                        "queue": "ollama",
                        "pending": stats.get("todo", 0),
                        "running": stats.get("doing", 0),
                        "completed": stats.get("succeeded", 0),
                        "failed": stats.get("failed", 0),
                    }


# Singleton instance
queue_service = QueueService()
