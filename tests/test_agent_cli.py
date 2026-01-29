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
