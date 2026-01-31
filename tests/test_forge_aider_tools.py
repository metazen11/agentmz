"""Tests for Forge Aider-backed edit tool."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.agent_cli import _build_tools


def _get_tool(name: str, workspace: Path):
    tools = _build_tools(str(workspace))
    for tool in tools:
        if tool.name == name:
            return tool
    raise AssertionError(f"Tool {name} not found")


def test_aider_edit_rejects_path_escape(tmp_path):
    tool = _get_tool("aider_edit", tmp_path)
    result = tool.invoke({"prompt": "touch", "files": ["../evil.txt"]})
    assert result["success"] is False
    assert "escape" in (result.get("error") or "").lower()


def test_aider_edit_invokes_aider_with_workspace_cwd(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None, env=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        captured["env"] = env or {}

        class Res:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Res()

    monkeypatch.setattr(subprocess, "run", fake_run)

    file_path = tmp_path / "app.py"
    file_path.write_text("print('hi')", encoding="utf-8")

    tool = _get_tool("aider_edit", tmp_path)
    result = tool.invoke({"prompt": "add a comment", "files": ["app.py"], "timeout": 30})

    assert result["success"] is True
    assert captured["cwd"] == str(tmp_path)
    assert captured["cmd"][0] == "aider"
    assert "--message" in captured["cmd"]
    assert "app.py" in captured["cmd"]
    assert captured["timeout"] == 30
    # Ensure env carries OLLAMA API base if set
    assert "OLLAMA_API_BASE" in captured["env"]


def test_aider_edit_defaults_files_to_workspace(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None, env=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env or {}

        class Res:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Res()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Two files in workspace; expect both passed when files not provided
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "b.js").write_text("console.log(1)", encoding="utf-8")

    tool = _get_tool("aider_edit", tmp_path)
    result = tool.invoke({"prompt": "add headers"})

    assert result["success"] is True
    assert "a.py" in captured["cmd"]
    assert "b.js" in captured["cmd"]
    assert captured["cwd"] == str(tmp_path)


def test_aider_edit_uses_model_env_defaults(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setenv("AIDER_MODEL", "ollama_chat/qwen3:test")
    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost:1234")

    def fake_run(cmd, cwd=None, capture_output=True, text=True, timeout=None, env=None):
        captured["cmd"] = cmd
        captured["env"] = env or {}

        class Res:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Res()

    monkeypatch.setattr(subprocess, "run", fake_run)

    tool = _get_tool("aider_edit", tmp_path)
    result = tool.invoke({"prompt": "noop"})

    assert result["success"] is True
    assert "--model" in captured["cmd"]
    model_arg_index = captured["cmd"].index("--model") + 1
    assert captured["cmd"][model_arg_index] == "ollama_chat/qwen3:test"
    assert captured["env"].get("OLLAMA_API_BASE") == "http://localhost:1234"
