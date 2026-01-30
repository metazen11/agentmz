"""Forge tests: create hello-world HTML per model with deterministic checks."""

import os
import re
import subprocess
import time
import threading
import sys
from datetime import datetime, timezone
from urllib import error, request

import pytest


def _log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")


def _stream_output(prefix: str, stream, lines: list[str], lock: threading.Lock) -> None:
    for raw in iter(stream.readline, ""):
        line = raw.rstrip()
        if line:
            with lock:
                lines.append(line)
            _log(f"{prefix} {line}")
    stream.close()


def _run_forge(prompt: str, model: str, workspace: str, env: dict, timeout: int = 240):
    start = time.monotonic()
    proc = subprocess.Popen(
        [
            sys.executable,
            os.path.join("scripts", "forge_runner.py"),
            "--prompt",
            prompt,
            "--model",
            model,
            "--workspace",
            workspace,
        ],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    lock = threading.Lock()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    stdout_thread = threading.Thread(
        target=_stream_output, args=("[forge stdout]", proc.stdout, stdout_lines, lock), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_stream_output, args=("[forge stderr]", proc.stderr, stderr_lines, lock), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    while True:
        if proc.poll() is not None:
            break
        if time.monotonic() - start > timeout:
            timed_out = True
            proc.terminate()
            break
        time.sleep(0.2)

    if timed_out:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    else:
        proc.wait()

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    elapsed = time.monotonic() - start
    return {
        "returncode": proc.returncode,
        "elapsed": elapsed,
        "timed_out": timed_out,
        "stdout_lines": stdout_lines,
        "stderr_lines": stderr_lines,
    }


def _log_workspace_snapshot(workspace: str) -> None:
    base = os.path.join("workspaces", workspace)
    if not os.path.isdir(base):
        _log(f"Workspace path missing: {base}")
        return
    entries = []
    for root, _, files in os.walk(base):
        rel_root = os.path.relpath(root, base)
        for name in files:
            rel = os.path.join(rel_root, name) if rel_root != "." else name
            entries.append(rel.replace("\\", "/"))
    entries = sorted(entries)
    _log(f"Workspace snapshot ({len(entries)} files): {entries[:20]}")


def _resolve_models() -> list[str]:
    raw = (
        os.environ.get("FORGE_MODEL_MATRIX")
        or os.environ.get("AGENT_CLI_MODEL")
        or os.environ.get("AGENT_MODEL")
        or ""
    )
    if not raw:
        return []
    parts = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts.append(chunk)
    return parts


def _sanitize_model(model: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", model).strip("-")
    return slug.lower() or "model"


def _ollama_base_url() -> str:
    return (
        os.environ.get("AGENT_CLI_OLLAMA_BASE")
        or os.environ.get("OLLAMA_API_BASE_LOCAL")
        or os.environ.get("OLLAMA_API_BASE")
        or "http://localhost:11435"
    )


def _ollama_models() -> list[str]:
    base_url = _ollama_base_url().rstrip("/")
    url = f"{base_url}/api/tags"
    try:
        with request.urlopen(url, timeout=5) as response:
            payload = response.read().decode("utf-8")
    except (OSError, error.URLError):
        return []
    try:
        import json
        data = json.loads(payload)
    except Exception:
        return []
    return [item.get("name", "") for item in data.get("models", [])]


def _model_available(model: str, available: list[str]) -> bool:
    if not available:
        return False
    model_core = model.replace("ollama_chat/", "")
    for entry in available:
        if entry == model_core:
            return True
        if entry.startswith(model_core):
            return True
        if model_core in entry:
            return True
    return False


MODELS = _resolve_models() or ["__none__"]


@pytest.mark.parametrize("model", MODELS)
def test_forge_creates_hello_world_html(model: str):
    if model == "__none__":
        pytest.skip("FORGE_MODEL_MATRIX or AGENT_CLI_MODEL not set")

    available = _ollama_models()
    if not _model_available(model, available):
        pytest.skip(f"Model not available in Ollama: {model}")

    slug = _sanitize_model(model)
    workspace = os.environ.get("FORGE_WORKSPACE") or "poc"
    filename = f"hello-world-{slug}.html"
    target_path = os.path.join("workspaces", workspace, filename)

    _log(f"Starting Forge HTML test for model={model} file={filename}")

    prompt = (
        "You are Forge, a system-agnostic coding agent. "
        f"Create a new file named {filename} in the workspace root. "
        "The file must be valid HTML5 with <!doctype html>, <html>, <head>, <body>. "
        "Include inline CSS and JS. "
        "Add at least two CSS animations: one for the background and one for text. "
        "Use write_file to create the file and do not create any other files."
    )

    env = os.environ.copy()
    env.setdefault("AGENT_CLI_TEMPERATURE", "0")
    env.setdefault("AGENT_CLI_TOOL_CHOICE", "any")
    env.setdefault("AGENT_CLI_TOOL_FALLBACK", "1")
    env.setdefault("AGENT_CLI_USE_LANGGRAPH", "0")

    env.setdefault("AGENT_CLI_MAX_ITERS", "4")

    run = _run_forge(prompt, model, workspace, env, timeout=240)
    _log(f"Forge elapsed={run['elapsed']:.2f}s timed_out={run['timed_out']}")

    if run["timed_out"]:
        _log("Forge timed out while creating HTML; checking for partial output.")
    else:
        _log(f"Forge exit code={run['returncode']}")
        if run["stdout_lines"]:
            _log(f"Forge stdout (tail): {run['stdout_lines'][-3:]}")
        if run["stderr_lines"]:
            _log(f"Forge stderr (tail): {run['stderr_lines'][-3:]}")
        assert run["returncode"] == 0, "Forge runner failed"
    if not os.path.isfile(target_path):
        _log("Expected file missing after first run; retrying with strict tool-call prompt.")
        _log_workspace_snapshot(workspace)
        strict_prompt = (
            "You are Forge. Output ONLY a JSON tool call for write_file with keys "
            '{"name":"write_file","arguments":{"path":"'
            + filename +
            '","content":"..."} }. '
            "The content must be valid HTML5 with <!doctype html>, <html>, <head>, <body>, "
            "inline CSS + JS, and at least two @keyframes animations (background + text). "
            "Do not include any prose."
        )
        strict_env = env.copy()
        strict_env["AGENT_CLI_DEBUG"] = "1"
        strict_env["AGENT_CLI_TOOL_FALLBACK"] = "1"
        strict_run = _run_forge(strict_prompt, model, workspace, strict_env, timeout=180)
        _log(f"Forge strict elapsed={strict_run['elapsed']:.2f}s timed_out={strict_run['timed_out']}")
        if strict_run["stdout_lines"]:
            _log(f"Forge strict stdout (tail): {strict_run['stdout_lines'][-3:]}")
        if strict_run["stderr_lines"]:
            _log(f"Forge strict stderr (tail): {strict_run['stderr_lines'][-3:]}")
        _log_workspace_snapshot(workspace)
    assert os.path.isfile(target_path), f"Expected file not found: {target_path}"
    stats = os.stat(target_path)
    _log(f"File stats: size={stats.st_size} mtime={stats.st_mtime}")

    with open(target_path, "r", encoding="utf-8", errors="ignore") as handle:
        content = handle.read()

    lower = content.lower()
    assert "<!doctype html" in lower
    assert "<html" in lower
    assert "<head" in lower
    assert "<body" in lower

    keyframes_count = len(re.findall(r"@keyframes", content, flags=re.IGNORECASE))
    animation_count = len(re.findall(r"animation\\s*:", content, flags=re.IGNORECASE))
    background_present = "background" in lower

    _log(
        f"HTML checks: keyframes={keyframes_count} animations={animation_count} background={background_present}"
    )

    if keyframes_count < 2 or animation_count < 2 or not background_present:
        _log("Animation checks failed; requesting Forge to improve file.")
        improve_prompt = (
            "You are Forge, a system-agnostic coding agent. "
            f"Improve the existing file {filename} to add at least two CSS @keyframes "
            "animations (background + text) and apply them to elements. "
            "Do not change the filename. Use read_file first, then apply_patch to update."
        )
        improve_run = _run_forge(improve_prompt, model, workspace, env, timeout=240)
        _log(f"Forge improve elapsed={improve_run['elapsed']:.2f}s timed_out={improve_run['timed_out']}")
        if improve_run["timed_out"]:
            _log("Forge timed out while improving HTML; re-checking file.")
        else:
            _log(f"Forge improve exit code={improve_run['returncode']}")
            if improve_run["stdout_lines"]:
                _log(f"Forge improve stdout (tail): {improve_run['stdout_lines'][-3:]}")
            if improve_run["stderr_lines"]:
                _log(f"Forge improve stderr (tail): {improve_run['stderr_lines'][-3:]}")
            assert improve_run["returncode"] == 0, "Forge runner failed on improve"
        with open(target_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
        lower = content.lower()
        keyframes_count = len(re.findall(r"@keyframes", content, flags=re.IGNORECASE))
        animation_count = len(re.findall(r"animation\\s*:", content, flags=re.IGNORECASE))
        background_present = "background" in lower
        _log(
            f"HTML checks after improve: keyframes={keyframes_count} animations={animation_count} background={background_present}"
        )

    assert keyframes_count >= 2, "Expected at least two @keyframes animations"
    assert animation_count >= 2, "Expected at least two animation declarations"
    assert background_present, "Expected background styling for animation"
