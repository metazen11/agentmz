"""Workspace registry and router for Forge."""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from forge.config import CONFIG_DIR


WORKSPACES_FILE = CONFIG_DIR / "workspaces.json"


@dataclass
class WorkspaceEntry:
    """A registered workspace entry."""
    id: str
    name: str
    root: str
    tags: list[str]
    repo_signatures: list[str]
    project_id: Optional[int]
    last_used: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceEntry":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            root=data.get("root", ""),
            tags=list(data.get("tags") or []),
            repo_signatures=list(data.get("repo_signatures") or []),
            project_id=data.get("project_id"),
            last_used=data.get("last_used"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "root": self.root,
            "tags": self.tags,
            "repo_signatures": self.repo_signatures,
            "project_id": self.project_id,
            "last_used": self.last_used,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_root(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def _load_registry() -> dict:
    if not WORKSPACES_FILE.exists():
        return {"default": None, "workspaces": []}
    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "workspaces" not in data:
            data["workspaces"] = []
        return data
    except Exception:
        return {"default": None, "workspaces": []}


def _save_registry(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def list_workspaces() -> list[WorkspaceEntry]:
    data = _load_registry()
    return [WorkspaceEntry.from_dict(w) for w in data.get("workspaces", [])]


def find_workspace(key: str) -> Optional[WorkspaceEntry]:
    key_lower = key.lower()
    for ws in list_workspaces():
        if ws.id == key:
            return ws
        if ws.name.lower() == key_lower:
            return ws
        if ws.root == key or _normalize_root(ws.root) == _normalize_root(key):
            return ws
    return None


def add_workspace(
    name: str,
    root: str,
    tags: Optional[Iterable[str]] = None,
    repo_signatures: Optional[Iterable[str]] = None,
    project_id: Optional[int] = None,
    set_default: bool = False,
) -> WorkspaceEntry:
    root_norm = _normalize_root(root)
    data = _load_registry()

    existing = find_workspace(root_norm)
    if existing:
        # Update existing entry
        existing.name = name or existing.name
        if tags is not None:
            existing.tags = list(tags)
        if repo_signatures is not None:
            existing.repo_signatures = list(repo_signatures)
        if project_id is not None:
            existing.project_id = project_id
        existing.root = root_norm
        if set_default:
            data["default"] = existing.id
        _replace_workspace(data, existing)
        _save_registry(data)
        return existing

    ws = WorkspaceEntry(
        id=f"ws_{uuid.uuid4().hex[:8]}",
        name=name,
        root=root_norm,
        tags=list(tags or []),
        repo_signatures=list(repo_signatures or []),
        project_id=project_id,
        last_used=None,
    )
    data["workspaces"].append(ws.to_dict())
    if set_default or not data.get("default"):
        data["default"] = ws.id
    _save_registry(data)
    return ws


def remove_workspace(key: str) -> bool:
    data = _load_registry()
    workspaces = data.get("workspaces", [])
    remaining = []
    removed_id = None
    for w in workspaces:
        ws = WorkspaceEntry.from_dict(w)
        if ws.id == key or ws.name.lower() == key.lower():
            removed_id = ws.id
            continue
        remaining.append(w)
    if removed_id is None:
        return False
    data["workspaces"] = remaining
    if data.get("default") == removed_id:
        data["default"] = remaining[0]["id"] if remaining else None
    _save_registry(data)
    return True


def set_default_workspace(key: str) -> bool:
    data = _load_registry()
    ws = find_workspace(key)
    if not ws:
        return False
    data["default"] = ws.id
    _save_registry(data)
    return True


def update_last_used(key: str) -> None:
    data = _load_registry()
    ws = find_workspace(key)
    if not ws:
        return
    ws.last_used = _utc_now()
    _replace_workspace(data, ws)
    _save_registry(data)


def _replace_workspace(data: dict, ws: WorkspaceEntry) -> None:
    updated = []
    for item in data.get("workspaces", []):
        if item.get("id") == ws.id:
            updated.append(ws.to_dict())
        else:
            updated.append(item)
    data["workspaces"] = updated


def _get_git_repo_name(path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if result.returncode != 0:
            return None
        top = result.stdout.strip()
        if not top:
            return None
        return os.path.basename(top)
    except Exception:
        return None


def _score_workspace(
    ws: WorkspaceEntry,
    cwd: str,
    hint: Optional[str],
    repo_name: Optional[str],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    ws_root = _normalize_root(ws.root)
    cwd_norm = _normalize_root(cwd)

    if cwd_norm == ws_root or cwd_norm.startswith(ws_root + os.sep):
        score += 100
        reasons.append("cwd_under_root")

    if repo_name:
        for sig in ws.repo_signatures:
            if sig.lower() == repo_name.lower():
                score += 40
                reasons.append("repo_signature_match")
                break

    if hint:
        hint_l = hint.lower()
        if ws.name.lower() == hint_l:
            score += 25
            reasons.append("name_match")
        if hint_l in [t.lower() for t in ws.tags]:
            score += 10
            reasons.append("tag_match")
        if hint_l in [s.lower() for s in ws.repo_signatures]:
            score += 10
            reasons.append("signature_match")

    return score, reasons


def resolve_workspace(
    cwd: Optional[str] = None,
    hint: Optional[str] = None,
    explicit: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve a workspace based on context.

    Returns a dict with keys:
      - root, id, name, project_id, score, reasons, source
    """
    cwd = cwd or os.getcwd()

    # If explicit path or name provided, honor it
    if explicit:
        ws = find_workspace(explicit)
        if ws:
            update_last_used(ws.id)
            return {
                "root": ws.root,
                "id": ws.id,
                "name": ws.name,
                "project_id": ws.project_id,
                "score": 999,
                "reasons": ["explicit_match"],
                "source": "explicit",
            }
        if os.path.isdir(explicit):
            return {
                "root": _normalize_root(explicit),
                "id": None,
                "name": None,
                "project_id": None,
                "score": 999,
                "reasons": ["explicit_path"],
                "source": "explicit",
            }

    registry = list_workspaces()
    if not registry:
        return {
            "root": _normalize_root(cwd),
            "id": None,
            "name": None,
            "project_id": None,
            "score": 0,
            "reasons": ["no_registry_fallback"],
            "source": "fallback",
        }

    repo_name = _get_git_repo_name(cwd)

    scored: list[tuple[int, WorkspaceEntry, list[str]]] = []
    for ws in registry:
        score, reasons = _score_workspace(ws, cwd=cwd, hint=hint, repo_name=repo_name)
        scored.append((score, ws, reasons))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_ws, reasons = scored[0]

    # If no score, prefer default or most recently used
    if best_score == 0:
        data = _load_registry()
        default_id = data.get("default")
        if default_id:
            ws = find_workspace(default_id)
            if ws:
                update_last_used(ws.id)
                return {
                    "root": ws.root,
                    "id": ws.id,
                    "name": ws.name,
                    "project_id": ws.project_id,
                    "score": 5,
                    "reasons": ["default_workspace"],
                    "source": "default",
                }
        # fallback: most recently used
        recent = sorted(
            registry,
            key=lambda w: w.last_used or "",
            reverse=True,
        )
        if recent:
            ws = recent[0]
            update_last_used(ws.id)
            return {
                "root": ws.root,
                "id": ws.id,
                "name": ws.name,
                "project_id": ws.project_id,
                "score": 3,
                "reasons": ["last_used"],
                "source": "last_used",
            }

    update_last_used(best_ws.id)
    return {
        "root": best_ws.root,
        "id": best_ws.id,
        "name": best_ws.name,
        "project_id": best_ws.project_id,
        "score": best_score,
        "reasons": reasons,
        "source": "scored",
    }
