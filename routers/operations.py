"""Routers for Director, Ops, and Env operations."""
import os
import time
import threading
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime

from database import get_db

router = APIRouter()

ENV_FILE_PATH = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent)).resolve() / ".env"
CONTAINER_NAMES = {
    "ollama": "wfhub-v2-ollama",
    "aider": "wfhub-v2-aider-api",
    "main": "wfhub-v2-main-api",
    "db": "wfhub-v2-db",
}

@router.get("/director/status")
def director_status():
    """Get director daemon status."""
    # TODO: Implement actual status check
    return {"running": False, "message": "Director not implemented yet"}


@router.post("/director/cycle")
def director_cycle(db: Session = Depends(get_db)):
    """Run one director cycle manually."""
    # TODO: Implement director cycle
    return {"message": "Director cycle not implemented yet"}


@router.post("/ops/restart/{service}")
def restart_service(service: str):
    """Restart a safe subset of containers via Docker."""
    import docker

    allowed = {"aider", "ollama"}
    if service not in allowed:
        raise HTTPException(status_code=404, detail="Service not supported for restart")

    container_name = CONTAINER_NAMES.get(service)
    if not container_name:
        raise HTTPException(status_code=404, detail="Unknown container")

    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        return {"success": True, "service": service, "container": container_name}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container {container_name} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _restart_services(services: list[str]) -> dict:
    import docker

    allowed = {"aider", "ollama", "main", "db"}
    invalid = [s for s in services if s not in allowed]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported services: {', '.join(invalid)}")

    client = docker.from_env()
    results = {}

    def restart_now(service_name: str):
        container_name = CONTAINER_NAMES.get(service_name)
        if not container_name:
            results[service_name] = {"success": False, "error": "Unknown container"}
            return
        try:
            container = client.containers.get(container_name)
            container.restart(timeout=10)
            results[service_name] = {"success": True, "container": container_name}
        except docker.errors.NotFound:
            results[service_name] = {"success": False, "error": "Container not found"}
        except Exception as exc:
            results[service_name] = {"success": False, "error": str(exc)}

    # Restart non-main services first to avoid self-restart mid-request
    for name in services:
        if name != "main":
            restart_now(name)

    if "main" in services:
        def delayed_restart():
            time.sleep(1)
            restart_now("main")
        threading.Thread(target=delayed_restart, daemon=True).start()
        results["main"] = {"success": True, "container": CONTAINER_NAMES.get("main"), "delayed": True}

    return results


def _parse_env_line(line: str) -> tuple[str, str, str, str] | None:
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        return None
    prefix, rest = line.split("=", 1)
    key = prefix.strip()
    if not key:
        return None
    value = rest.rstrip("\n")
    return key, prefix + "=", value, "\n" if line.endswith("\n") else ""


def _read_env_file() -> list[dict]:
    if not ENV_FILE_PATH.exists():
        return []
    entries = []
    with ENV_FILE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle.readlines():
            stripped = line.rstrip("\n")
            if not stripped:
                entries.append({"type": "blank"})
                continue
            if stripped.lstrip().startswith("#") or "=" not in stripped:
                entries.append({"type": "comment", "value": stripped})
                continue
            parsed = _parse_env_line(stripped)
            if not parsed:
                entries.append({"type": "comment", "value": stripped})
                continue
            key, _, value, _ = parsed
            entries.append({"type": "pair", "key": key, "value": value})
    return entries


def _write_env_file(updates: dict) -> list[str]:
    if not ENV_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail=".env not found")

    updated_keys = []
    seen_keys = set()
    new_lines = []

    backup_text = ENV_FILE_PATH.read_text(encoding="utf-8")
    backup_path = ENV_FILE_PATH.with_suffix(".env_bak.txt")
    backup_path.write_text(backup_text, encoding="utf-8")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    history_path = ENV_FILE_PATH.with_name(f".env_bak_{timestamp}.txt")
    history_path.write_text(backup_text, encoding="utf-8")
    with ENV_FILE_PATH.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    for line in lines:
        parsed = _parse_env_line(line)
        if not parsed:
            new_lines.append(line)
            continue
        key, prefix, value, newline = parsed
        seen_keys.add(key)
        if key in updates:
            new_value = str(updates[key])
            new_lines.append(f"{prefix}{new_value}{newline}")
            updated_keys.append(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen_keys:
            new_lines.append(f"{key}={value}\n")
            updated_keys.append(key)

    ENV_FILE_PATH.write_text("".join(new_lines), encoding="utf-8")
    return updated_keys


@router.get("/api/env")
def get_env_settings():
    """Return .env entries for editing."""
    return {"success": True, "entries": _read_env_file()}


@router.post("/api/env")
def update_env_settings(payload: dict):
    """Update .env values and restart services if requested."""
    updates = payload.get("updates", {})
    if not isinstance(updates, dict):
        raise HTTPException(status_code=400, detail="updates must be an object")

    updated_keys = _write_env_file(updates)
    services = payload.get("restart_services", [])
    if services:
        restart_results = _restart_services(services)
    else:
        restart_results = {}
    return {"success": True, "updated_keys": updated_keys, "restarted": restart_results}
