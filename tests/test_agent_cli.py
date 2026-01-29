import os


def test_agent_cli_defaults_prefer_explicit_env(monkeypatch):
    monkeypatch.setenv("AGENT_CLI_MODEL", "cli-model")
    monkeypatch.setenv("AGENT_CLI_OLLAMA_BASE", "http://cli-ollama:11434")
    monkeypatch.setenv("AGENT_CLI_WORKSPACE", "cli_workspace")
    monkeypatch.setenv("AGENT_CLI_PROJECT_NAME", "demo-project")
    monkeypatch.setenv("AGENT_CLI_USE_LANGGRAPH", "true")
    monkeypatch.setenv("AGENT_CLI_MAX_ITERS", "9")
    monkeypatch.setenv("AGENT_MODEL", "fallback-model")
    monkeypatch.setenv("OLLAMA_API_BASE_LOCAL", "http://local-ollama:11434")
    monkeypatch.setenv("OLLAMA_API_BASE", "http://base-ollama:11434")
    monkeypatch.setenv("DEFAULT_WORKSPACE", "default_workspace")

    from scripts import agent_cli

    defaults = agent_cli._resolve_defaults(os.environ)
    assert defaults["model"] == "cli-model"
    assert defaults["base_url"] == "http://cli-ollama:11434"
    assert defaults["workspace"] == "cli_workspace"
    assert defaults["project_name"] == "demo-project"
    assert defaults["use_langgraph"] is True
    assert defaults["max_iters"] == 9


def test_agent_cli_defaults_fallback_to_shared_env(monkeypatch):
    monkeypatch.delenv("AGENT_CLI_MODEL", raising=False)
    monkeypatch.delenv("AGENT_CLI_OLLAMA_BASE", raising=False)
    monkeypatch.delenv("AGENT_CLI_WORKSPACE", raising=False)
    monkeypatch.delenv("AGENT_CLI_PROJECT_NAME", raising=False)
    monkeypatch.delenv("AGENT_CLI_USE_LANGGRAPH", raising=False)
    monkeypatch.delenv("AGENT_CLI_MAX_ITERS", raising=False)
    monkeypatch.setenv("AGENT_MODEL", "agent-model")
    monkeypatch.setenv("OLLAMA_API_BASE_LOCAL", "http://local-ollama:11434")
    monkeypatch.setenv("DEFAULT_WORKSPACE", "shared_workspace")

    from scripts import agent_cli

    defaults = agent_cli._resolve_defaults(os.environ)
    assert defaults["model"] == "agent-model"
    assert defaults["base_url"] == "http://local-ollama:11434"
    assert defaults["workspace"] == "shared_workspace"
    assert defaults["project_name"] == ""
    assert defaults["use_langgraph"] is False
    assert defaults["max_iters"] == 6


def test_apply_patch_replaces_line():
    from scripts import agent_cli

    original = "alpha\nbeta\ngamma\n"
    patch = (
        "--- a/sample.txt\n"
        "+++ b/sample.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+BETA\n"
        " gamma\n"
    )
    updated = agent_cli._apply_unified_patch(original, patch)
    assert updated == "alpha\nBETA\ngamma\n"


def test_apply_patch_adds_line():
    from scripts import agent_cli

    original = "alpha\nbeta\n"
    patch = (
        "--- a/sample.txt\n"
        "+++ b/sample.txt\n"
        "@@ -1,2 +1,3 @@\n"
        " alpha\n"
        "+inserted\n"
        " beta\n"
    )
    updated = agent_cli._apply_unified_patch(original, patch)
    assert updated == "alpha\ninserted\nbeta\n"


def test_apply_patch_removes_line():
    from scripts import agent_cli

    original = "alpha\nbeta\ngamma\n"
    patch = (
        "--- a/sample.txt\n"
        "+++ b/sample.txt\n"
        "@@ -1,3 +1,2 @@\n"
        " alpha\n"
        "-beta\n"
        " gamma\n"
    )
    updated = agent_cli._apply_unified_patch(original, patch)
    assert updated == "alpha\ngamma\n"


def test_apply_patch_invalid_context_raises():
    from scripts import agent_cli

    original = "alpha\nbeta\ngamma\n"
    patch = (
        "--- a/sample.txt\n"
        "+++ b/sample.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-notbeta\n"
        "+BETA\n"
        " gamma\n"
    )
    try:
        agent_cli._apply_unified_patch(original, patch)
    except ValueError as exc:
        assert "Patch context mismatch" in str(exc)
        return
    raise AssertionError("Expected ValueError for invalid patch context")


def test_tool_file_ops_with_temp_workspace(tmp_path):
    from scripts import agent_cli

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tools = agent_cli._build_tools(str(workspace))
    tool_map = {tool.name: tool for tool in tools}

    mkdir = tool_map["mkdir"]
    write_file = tool_map["write_file"]
    stat_path = tool_map["stat_path"]
    copy_file = tool_map["copy_file"]
    move_file = tool_map["move_file"]
    delete_file = tool_map["delete_file"]
    list_tree = tool_map["list_tree"]

    mkdir.invoke({"path": "nested/dir"})
    write_file.invoke({"path": "nested/dir/sample.txt", "content": "hello"})

    stat = stat_path.invoke({"path": "nested/dir/sample.txt"})
    assert stat["success"] is True
    assert stat["is_file"] is True

    copied = copy_file.invoke({"src": "nested/dir/sample.txt", "dst": "nested/dir/copied.txt"})
    assert copied["success"] is True

    moved = move_file.invoke({"src": "nested/dir/copied.txt", "dst": "nested/dir/moved.txt"})
    assert moved["success"] is True

    tree = list_tree.invoke({"path": ".", "max_depth": 3})
    assert tree["success"] is True
    assert any(item.endswith("nested/dir/moved.txt") for item in tree["files"])

    deleted = delete_file.invoke({"path": "nested/dir/moved.txt"})
    assert deleted["success"] is True

    deleted_dir = delete_file.invoke({"path": "nested", "recursive": True})
    assert deleted_dir["success"] is True
