"""Routers for Container Log Streaming."""
import asyncio
import os
import json
import time
import itertools
from datetime import datetime, timezone
from collections import deque
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx

router = APIRouter()

# Container names to stream logs from
CONTAINER_NAMES = {
    "ollama": "wfhub-v2-ollama",
    "aider": "wfhub-v2-aider-api",
    "main": "wfhub-v2-main-api",
    "db": "wfhub-v2-db",
}

INTERNAL_LOG_SOURCES = {"ollama_http"}
OLLAMA_HTTP_LOG_BUFFER = deque(maxlen=500)
OLLAMA_HTTP_CLIENTS = set()
OLLAMA_HTTP_LOG_LOCK = asyncio.Lock()
OLLAMA_HTTP_REQUEST_ID = itertools.count(1)
OLLAMA_HTTP_LOG_MAX_BYTES = int(os.getenv("OLLAMA_HTTP_LOG_MAX_BYTES", "8192"))
# 0 = no truncation, any positive number = character limit
OLLAMA_HTTP_LOG_TRUNCATE_LIMIT = int(os.getenv("OLLAMA_HTTP_LOG_TRUNCATE_LIMIT", "0"))


def _truncate_text(text: str, limit: int | None = None) -> str:
    if not text:
        return ""
    if limit is None:
        limit = OLLAMA_HTTP_LOG_TRUNCATE_LIMIT
    flat = " ".join(text.split())
    if limit > 0 and len(flat) > limit:
        return f"{flat[:limit]}..."
    return flat


def _format_ollama_request_summary(method: str, path: str, body: bytes) -> str:
    summary = f"{method} /{path}"
    if not body:
        return summary
    try:
        payload = json.loads(body)
    except Exception:
        return f"{summary} body={len(body)} bytes"
    details = []
    model = payload.get("model")
    if model:
        details.append(f"model={model}")
    if "stream" in payload:
        details.append(f"stream={payload.get('stream')}")
    if "prompt" in payload:
        details.append(f'prompt="{_truncate_text(str(payload.get("prompt", "")))}"')
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last_msg = messages[-1].get("content", "")
        details.append(f'messages={len(messages)} last="{_truncate_text(str(last_msg))}"')
    if details:
        return f"{summary} " + " ".join(details)
    return summary


def _extract_ollama_output_snippet(snippet_text: str) -> str:
    if not snippet_text:
        return ""
    for line in reversed([l for l in snippet_text.splitlines() if l.strip()]):
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if "response" in payload:
            return _truncate_text(str(payload.get("response", "")))
        message = payload.get("message")
        if isinstance(message, dict) and "content" in message:
            return _truncate_text(str(message.get("content", "")))
        if "error" in payload:
            return _truncate_text(str(payload.get("error", "")))
    return _truncate_text(snippet_text)


async def append_ollama_http_log(line: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    line = f"[{timestamp}] {line}"
    async with OLLAMA_HTTP_LOG_LOCK:
        OLLAMA_HTTP_LOG_BUFFER.append(line)
        stale = []
        for ws in list(OLLAMA_HTTP_CLIENTS):
            try:
                await ws.send_text(line)
            except Exception:
                stale.append(ws)
        for ws in stale:
            OLLAMA_HTTP_CLIENTS.discard(ws)


async def stream_container_logs(websocket: WebSocket, container_name: str):
    """Stream logs from a Docker container via WebSocket without blocking the event loop."""
    import docker
    import queue
    import threading

    log_queue: "queue.Queue[bytes | None]" = queue.Queue()
    stop_event = threading.Event()

    def _producer():
        try:
            client = docker.from_env()
            container = client.containers.get(container_name)
            for log_line in container.logs(stream=True, follow=True, tail=100):
                if stop_event.is_set():
                    break
                log_queue.put(log_line)
        except Exception:
            log_queue.put(None)
        finally:
            log_queue.put(None)

    thread = threading.Thread(target=_producer, daemon=True)
    thread.start()

    try:
        while True:
            log_line = await asyncio.to_thread(log_queue.get)
            if log_line is None:
                break
            line = log_line.decode("utf-8", errors="replace").strip()
            if line:
                await websocket.send_text(line)
    except WebSocketDisconnect:
        stop_event.set()
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {str(e)}")
        except Exception:
            pass
    finally:
        stop_event.set()


@router.websocket("/ws/logs/{container}")
async def websocket_logs(websocket: WebSocket, container: str):
    """WebSocket endpoint to stream container logs.

    Usage: ws://localhost:8002/ws/logs/ollama
    Available containers: ollama, aider, main, db, ollama_http
    """
    await websocket.accept()

    if container in INTERNAL_LOG_SOURCES:
        try:
            for line in list(OLLAMA_HTTP_LOG_BUFFER):
                await websocket.send_text(line)
            OLLAMA_HTTP_CLIENTS.add(websocket)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            OLLAMA_HTTP_CLIENTS.discard(websocket)
        return

    container_name = CONTAINER_NAMES.get(container)
    if not container_name:
        await websocket.send_text(f"Unknown container: {container}")
        await websocket.send_text(
            f"Available: {', '.join(sorted(CONTAINER_NAMES.keys() | INTERNAL_LOG_SOURCES))}"
        )
        await websocket.close()
        return

    try:
        await websocket.send_text(f"=== Streaming logs from {container_name} ===")
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close()
        return

    try:
        await stream_container_logs(websocket, container_name)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {str(e)}")
        except Exception:
            pass


@router.get("/logs/{container}")
async def get_recent_logs(container: str, lines: int = 100):
    """Get recent logs from a container (non-streaming)."""
    import docker

    if container in INTERNAL_LOG_SOURCES:
        logs = "\n".join(list(OLLAMA_HTTP_LOG_BUFFER)[-lines:])
        return {"container": container, "lines": lines, "logs": logs}

    container_name = CONTAINER_NAMES.get(container)
    if not container_name:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown container: {container}. Available: "
                f"{', '.join(sorted(CONTAINER_NAMES.keys() | INTERNAL_LOG_SOURCES))}"
            ),
        )

    try:
        client = docker.from_env()
        container_obj = client.containers.get(container_name)
        logs = container_obj.logs(tail=lines).decode("utf-8", errors="replace")
        return {"container": container_name, "lines": lines, "logs": logs}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route("/ollama/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_ollama(path: str, request: Request):
    """Proxy Ollama API calls and log request/response details."""
    target_base = os.getenv(
        "OLLAMA_PROXY_TARGET",
        os.getenv("OLLAMA_API_BASE", "http://wfhub-v2-ollama:11434"),
    ).rstrip("/")
    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    request_id = next(OLLAMA_HTTP_REQUEST_ID)
    body = await request.body()
    request_summary = _format_ollama_request_summary(request.method, path, body)
    await append_ollama_http_log(f"[ollama-http] -> {request_id} {request_summary}")
    start_time = time.monotonic()

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }

    client = httpx.AsyncClient(timeout=None)
    stream = client.stream(
        request.method,
        target_url,
        content=body or None,
        headers=headers,
    )
    try:
        response = await stream.__aenter__()
    except Exception as e:
        await client.aclose()
        await append_ollama_http_log(f"[ollama-http] !! {request_id} proxy_error={e}")
        raise HTTPException(status_code=502, detail="Failed to reach Ollama") from e

    response_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in {"transfer-encoding", "connection", "content-length"}
    }

    async def stream_response():
        snippet = bytearray()
        total_bytes = 0
        try:
            async for chunk in response.aiter_bytes():
                total_bytes += len(chunk)
                if len(snippet) < OLLAMA_HTTP_LOG_MAX_BYTES:
                    snippet.extend(chunk[:OLLAMA_HTTP_LOG_MAX_BYTES - len(snippet)])
                yield chunk
        finally:
            duration = time.monotonic() - start_time
            snippet_text = snippet.decode("utf-8", errors="replace")
            output = _extract_ollama_output_snippet(snippet_text)
            output_part = f' output="{output}"' if output else ""
            await append_ollama_http_log(
                f"[ollama-http] <- {request_id} {response.status_code} "
                f"{duration:.2f}s bytes={total_bytes}{output_part}"
            )
            await response.aclose()
            await stream.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(
        stream_response(),
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )
