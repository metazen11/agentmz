#!/usr/bin/env python3
"""
Run Forge tests one model at a time with streaming output + timestamps.

Usage:
  python scripts/run_forge_matrix.py --tests html
  python scripts/run_forge_matrix.py --tests js
  python scripts/run_forge_matrix.py --tests both
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone


def _log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] {message}")


def _stream_output(prefix: str, stream) -> None:
    for raw in iter(stream.readline, ""):
        line = raw.rstrip()
        if line:
            _log(f"{prefix} {line}")
    stream.close()


def _resolve_models() -> list[str]:
    raw = os.environ.get("FORGE_MODEL_MATRIX", "")
    if not raw:
        return []
    parts = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def _run_pytest(args: list[str], env: dict, timeout: int) -> int:
    start = time.monotonic()
    proc = subprocess.Popen(
        args,
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    out_thread = threading.Thread(target=_stream_output, args=("[pytest stdout]", proc.stdout), daemon=True)
    err_thread = threading.Thread(target=_stream_output, args=("[pytest stderr]", proc.stderr), daemon=True)
    out_thread.start()
    err_thread.start()

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
        _log("pytest timed out; terminating process")
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    else:
        proc.wait()

    out_thread.join(timeout=2)
    err_thread.join(timeout=2)
    elapsed = time.monotonic() - start
    _log(f"pytest finished rc={proc.returncode} elapsed={elapsed:.2f}s")
    return proc.returncode or 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Forge tests per model")
    parser.add_argument("--tests", choices=["html", "js", "both"], default="both")
    parser.add_argument("--timeout", type=int, default=900, help="Timeout per model (seconds)")
    args = parser.parse_args()

    models = _resolve_models()
    if not models:
        _log("FORGE_MODEL_MATRIX is empty. Set it before running this script.")
        return 1

    test_files = []
    if args.tests in {"html", "both"}:
        test_files.append("tests/test_forge_html_models.py")
    if args.tests in {"js", "both"}:
        test_files.append("tests/test_forge_js_models.py")

    exit_code = 0
    for model in models:
        _log(f"=== Running Forge tests for model: {model} ===")
        env = os.environ.copy()
        env["FORGE_MODEL_MATRIX"] = model
        cmd = [sys.executable, "-m", "pytest", *test_files, "-v", "-s"]
        rc = _run_pytest(cmd, env, timeout=args.timeout)
        if rc != 0:
            exit_code = rc
        _log(f"=== Done model: {model} (rc={rc}) ===")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
