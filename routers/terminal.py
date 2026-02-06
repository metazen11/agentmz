"""WebSocket terminal access for Docker containers."""
import asyncio
import json
import os
import re
import shlex
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

CONTAINER_NAMES = {
    "aider": "wfhub-v2-aider-api",
    "main": "wfhub-v2-main-api",
    "ollama": "wfhub-v2-ollama",
    "db": "wfhub-v2-db",
}

CONTAINER_ROOTS = {
    "aider": "/v2",
    "main": "/app",
}

DEFAULT_WORKDIRS = {
    "aider": "/workspaces",
    "main": "/app",
    "ollama": "/",
    "db": "/",
}

ALLOWED_WORKDIR_ROOTS = {
    "aider": ["/v2", "/workspaces"],
    "main": ["/app", "/workspaces"],
    "ollama": ["/"],
    "db": ["/"],
}

DEFAULT_SHELL = os.getenv("TERMINAL_SHELL", "bash")
MAX_INPUT_BYTES = int(os.getenv("TERMINAL_MAX_INPUT_BYTES", "8192"))
DEFAULT_PS1 = os.getenv("TERMINAL_PS1", r"[\u@\h:\w]\$ ")


def _normalize_workspace_value(value: str) -> str:
    if not value:
        return ""
    cleaned = value.replace("\\", "/").strip()
    if cleaned.startswith("[%root%]"):
        return cleaned
    marker = "/workspaces/"
    lowered = cleaned.lower()
    idx = lowered.rfind(marker)
    if idx != -1:
        cleaned = cleaned[idx + len(marker):]
    cleaned = re.sub(r"^\.?/?(workspaces/)?", "", cleaned)
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return "/".join(parts)


def _sanitize_workdir(container: str, workdir: str) -> str:
    cleaned = "/" + workdir.replace("\\", "/").lstrip("/")
    cleaned = re.sub(r"/+", "/", cleaned)
    allowed_roots = ALLOWED_WORKDIR_ROOTS.get(container, ["/"])
    for root in allowed_roots:
        if cleaned == root or cleaned.startswith(root.rstrip("/") + "/"):
            return cleaned
    return DEFAULT_WORKDIRS.get(container, "/")


def _workspace_to_workdir(container: str, workspace: str) -> str:
    normalized = _normalize_workspace_value(workspace)
    if normalized.startswith("[%root%]"):
        root = CONTAINER_ROOTS.get(container, "/")
        suffix = normalized.replace("[%root%]", "").lstrip("/")
        target = root if not suffix else f"{root}/{suffix}"
        return _sanitize_workdir(container, target)
    if not normalized:
        return DEFAULT_WORKDIRS.get(container, "/")
    return _sanitize_workdir(container, f"/workspaces/{normalized}")


def _resolve_workdir(container: str, params) -> str:
    raw_workdir = (params.get("workdir") or "").strip()
    if raw_workdir:
        return _sanitize_workdir(container, raw_workdir)
    workspace = (params.get("workspace") or "").strip()
    if workspace:
        return _workspace_to_workdir(container, workspace)
    return DEFAULT_WORKDIRS.get(container, "/")


def _socket_send(sock, payload: bytes) -> None:
    if not payload:
        return
    try:
        if hasattr(sock, "send"):
            sock.send(payload)
        elif hasattr(sock, "write"):
            sock.write(payload)
        elif hasattr(sock, "_sock"):
            sock._sock.send(payload)
    except Exception:
        pass


def _socket_recv(sock, size: int = 4096) -> bytes:
    if hasattr(sock, "recv"):
        return sock.recv(size)
    if hasattr(sock, "read"):
        return sock.read(size)
    if hasattr(sock, "_sock"):
        return sock._sock.recv(size)
    return b""


def _socket_close(sock) -> None:
    try:
        if hasattr(sock, "close"):
            sock.close()
        elif hasattr(sock, "_sock"):
            sock._sock.close()
    except Exception:
        pass


def _extract_input(message: str) -> str:
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return message
    if isinstance(payload, dict) and payload.get("type") == "input":
        return str(payload.get("data", ""))
    return ""


def _start_exec_socket(container_name: str, shell: str, workdir: str):
    import docker

    client = docker.from_env()
    container = client.containers.get(container_name)
    shell_cmd = _build_shell_command(shell)
    env_vars = {"TERM": "xterm-256color"}
    shell_name = os.path.basename(shell_cmd[0])
    if shell_name == "bash":
        env_vars["PS1"] = DEFAULT_PS1
    exec_id = client.api.exec_create(
        container.id,
        cmd=shell_cmd,
        tty=True,
        stdin=True,
        workdir=workdir,
        environment=env_vars,
    )
    return client.api.exec_start(exec_id, tty=True, socket=True)


def _build_shell_command(shell: str) -> list[str]:
    cleaned = shell.strip() if shell else DEFAULT_SHELL
    try:
        parts = shlex.split(cleaned)
    except ValueError:
        parts = [cleaned]
    if not parts:
        parts = [DEFAULT_SHELL]
    shell_name = os.path.basename(parts[0])
    if shell_name in {"bash", "sh"} and all(arg not in {"-i", "--interactive"} for arg in parts[1:]):
        parts.append("-i")
    return parts


@router.websocket("/ws/terminal/{container}")
async def websocket_terminal(websocket: WebSocket, container: str):
    await websocket.accept()

    container_name = CONTAINER_NAMES.get(container)
    if not container_name:
        await websocket.send_text(
            f"Unknown container: {container}. Available: {', '.join(sorted(CONTAINER_NAMES))}"
        )
        await websocket.close()
        return

    shell = (websocket.query_params.get("shell") or DEFAULT_SHELL).strip() or DEFAULT_SHELL
    workdir = _resolve_workdir(container, websocket.query_params)

    try:
        sock = _start_exec_socket(container_name, shell, workdir)
    except Exception as exc:
        await websocket.send_text(f"Failed to start terminal: {exc}")
        await websocket.close()
        return

    await websocket.send_text(f"=== Connected to {container_name} ({workdir}) ===")

    loop = asyncio.get_running_loop()
    queue: "asyncio.Queue[str | None]" = asyncio.Queue()
    stop_event = threading.Event()

    def _reader():
        try:
            while not stop_event.is_set():
                chunk = _socket_recv(sock)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                loop.call_soon_threadsafe(queue.put_nowait, text)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()

    async def _send_output():
        while True:
            item = await queue.get()
            if item is None:
                break
            try:
                await websocket.send_text(item)
            except WebSocketDisconnect:
                break

    async def _receive_input():
        while True:
            try:
                message = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            data = _extract_input(message)
            if not data:
                continue
            payload = data.encode("utf-8")
            if len(payload) > MAX_INPUT_BYTES:
                payload = payload[:MAX_INPUT_BYTES]
            _socket_send(sock, payload)

    send_task = asyncio.create_task(_send_output())
    recv_task = asyncio.create_task(_receive_input())
    done, pending = await asyncio.wait(
        [send_task, recv_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    for task in done:
        try:
            task.result()
        except Exception:
            pass
    stop_event.set()
    _socket_close(sock)
