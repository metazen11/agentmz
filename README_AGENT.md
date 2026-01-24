# AgentMZ - AI Coding Assistant

A self-contained AI coding agent stack that auto-installs, configures, and runs locally with Ollama + Aider.

## Quick Start

```bash
# 1. Start the stack (auto-installs everything)
./start.sh

# 2. Reload shell to get 'agent' command
source ~/.bashrc

# 3. Start coding
agent
```

That's it. The stack handles Docker, Ollama models, aider, and shell configuration automatically.

## What Gets Installed

| Component | Description | Auto-Install |
|-----------|-------------|--------------|
| Docker services | Ollama, Aider API, Main API, Caddy | via docker-compose |
| Ollama models | qwen3:0.6b, qwen3:1.7b, etc. | pulled on first run |
| Aider | AI coding assistant | pip install --user |
| Agent command | Shell alias for easy access | added to .bashrc/.zshrc |
| AGENTMZ_DIR | Environment variable | exported in shell rc |

## Agent Command

### Basic Usage

```bash
agent                              # Interactive session
agent -p "Fix the bug" main.py     # Inline prompt
agent -pf task.txt                 # Prompt from file
agent -w ./myproject -p "Add tests" # Specify workspace
```

### Model Selection

```bash
agent -s1 ...   # qwen3:0.6b (smallest, fastest)
agent -s2 ...   # qwen3:1.7b (small, good quality)
agent -s3 ...   # qwen2.5-coder:3b (medium, coding optimized)
agent -s4 ...   # qwen2.5-coder:7b (large, best quality)
```

### YOLO Mode (Non-Interactive)

```bash
agent --yolo -p "Refactor this function" utils.py
```

### Chained Iterations (Auto-Verify)

```bash
# Run prompt + 1 verify pass
agent --yolo --verify -p "Add authentication" auth.py

# Run prompt + 3 verify passes
agent --yolo --verify --iterations 3 -p "Major refactor" src/
```

The verify pass reviews changes and fixes bugs, errors, or intent mismatches.

### Vision (Images)

```bash
agent -i screenshot.png -p "Implement this UI design"
```

### All Options

```
agent --help

Options:
  -p, --prompt "text"     Inline prompt
  -pf, --prompt-file FILE Read prompt from file
  -w, --workspace DIR     Working directory (default: cwd)
  -i, --image FILE        Include image (vision models)
  -m, --model MODEL       Model name
  -s1 to -s4              Model size shortcuts
  --yolo                  Auto-yes, non-interactive
  --verify                Chain: run + verify/fix
  --iterations N          Number of verify passes (default: 1)
  -v, --verbose           Debug output
  -h, --help              Show help
```

## Helper Commands

```bash
agent-config    # Interactive wizard (model, endpoint)
agent-model     # Quick model switch
agent-model 2   # Switch to model #2
```

## Manual Installation

If auto-install didn't work:

```bash
# Install aider + register agent command
./agent_alias_install.sh

# Reload shell
source ~/.bashrc
```

## Architecture

```
start.sh
   |
   +-- Docker Compose
   |      +-- wfhub-v2-ollama (LLM server, port 11435)
   |      +-- wfhub-v2-main-api (API + Ollama proxy, port 8002)
   |      +-- wfhub-v2-aider-api (Aider service, port 8001)
   |      +-- wfhub-v2-caddy (HTTPS proxy)
   |
   +-- agent_alias_install.sh
          +-- Installs aider via pip
          +-- Sets AGENTMZ_DIR
          +-- Sources wrapper_init.sh in .bashrc/.zshrc

agent (shell command)
   |
   +-- agent.sh
          +-- Parses arguments
          +-- Sets workspace (cwd if not specified)
          +-- Configures Ollama endpoint
          +-- Runs aider with options
          +-- Optionally chains verify iterations
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTMZ_DIR` | Project root | Set by installer |
| `AIDER_MODEL` | Default model | ollama_chat/qwen3:0.6b |
| `OLLAMA_API_BASE` | Ollama endpoint | http://localhost:8002/ollama |
| `OLLAMA_API_BASE_LOCAL` | Local override | (from .env) |

## WSL Notes

- Docker Desktop must be installed on Windows with WSL integration enabled
- `start.sh` auto-detects WSL and starts Docker Desktop if needed
- Browser opens via Windows (cmd.exe/powershell.exe)
- Paths use `/mnt/c/...` format

## Troubleshooting

### Docker not starting
```bash
# Check Docker Desktop is installed and WSL integration is enabled
docker info
```

### Ollama models not loading
```bash
# Check Ollama is running
curl http://localhost:11435/api/tags

# Pull model manually
docker exec wfhub-v2-ollama ollama pull qwen3:0.6b
```

### Agent command not found
```bash
# Re-run installer
./agent_alias_install.sh
source ~/.bashrc

# Check AGENTMZ_DIR is set
echo $AGENTMZ_DIR
```

### Aider can't connect to Ollama
```bash
# Test endpoint
curl http://localhost:8002/ollama/api/tags

# Check .env has correct OLLAMA_API_BASE_LOCAL
cat .env | grep OLLAMA
```

## Files

| File | Purpose |
|------|---------|
| `start.sh` | Main startup script |
| `agent.sh` | Agent CLI implementation |
| `agent_alias_install.sh` | Installs agent command |
| `wrapper_init.sh` | Shell functions (agent, agent-config, agent-model) |
| `run_aider.sh` | Docker-based aider (alternative) |
| `run_aider_local.sh` | Local aider with auto-config |
| `.env` | Configuration |
| `.aiderignore` | Files excluded from repo-map |
