#!/usr/bin/env bash

# Use AGENTMZ_DIR if set, otherwise derive from script location
if [ -n "${AGENTMZ_DIR:-}" ]; then
  script_dir="$AGENTMZ_DIR"
else
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ ! -f "${script_dir}/agent.sh" ]; then
  echo "agent.sh not found in ${script_dir}" >&2
  return 1 2>/dev/null || exit 1
fi

# Available models (smallest to largest)
_AGENT_MODELS=("qwen3:0.6b" "qwen3:1.7b" "qwen2.5-coder:3b" "qwen2.5-coder:7b")

# Interactive wizard for agent configuration
agent-config() {
  echo "=== Agent Configuration Wizard ==="
  echo ""

  # Model selection
  echo "Select model:"
  local i=1
  for m in "${_AGENT_MODELS[@]}"; do
    echo "  $i) $m"
    ((i++))
  done
  echo ""
  read -p "Choice [1]: " model_choice
  model_choice="${model_choice:-1}"

  if [[ "$model_choice" =~ ^[1-4]$ ]]; then
    local selected_model="${_AGENT_MODELS[$((model_choice-1))]}"
    export AIDER_MODEL="ollama_chat/${selected_model}"
    export AGENT_MODEL="$selected_model"
    echo "Model set to: $selected_model"
  else
    echo "Invalid choice, keeping current model"
  fi

  echo ""

  # Ollama endpoint
  echo "Ollama endpoint options:"
  echo "  1) http://localhost:8002/ollama (via main-api proxy)"
  echo "  2) http://localhost:11435 (direct Ollama)"
  echo "  3) Custom URL"
  echo ""
  read -p "Choice [1]: " ollama_choice
  ollama_choice="${ollama_choice:-1}"

  case "$ollama_choice" in
    1) export OLLAMA_API_BASE="http://localhost:8002/ollama" ;;
    2) export OLLAMA_API_BASE="http://localhost:11435" ;;
    3)
      read -p "Enter Ollama URL: " custom_url
      export OLLAMA_API_BASE="$custom_url"
      ;;
    *) echo "Invalid choice, keeping current endpoint" ;;
  esac

  echo "Ollama endpoint: $OLLAMA_API_BASE"
  echo ""
  echo "Configuration complete! Run 'agent' to start."
}

# Quick model switch
agent-model() {
  if [ -z "${1:-}" ]; then
    echo "Current model: ${AIDER_MODEL:-not set}"
    echo ""
    echo "Usage: agent-model <number>"
    local i=1
    for m in "${_AGENT_MODELS[@]}"; do
      echo "  $i) $m"
      ((i++))
    done
    return
  fi

  if [[ "$1" =~ ^[1-4]$ ]]; then
    local selected_model="${_AGENT_MODELS[$(($1-1))]}"
    export AIDER_MODEL="ollama_chat/${selected_model}"
    export AGENT_MODEL="$selected_model"
    echo "Model set to: $selected_model"
  else
    echo "Invalid choice (1-4)"
  fi
}

# Main alias - type 'agent' to run aider with local config
agent() {
  "${script_dir}/agent.sh" "$@"
}

# Alias for backward compatibility
aicoder() {
  "${script_dir}/agent.sh" "$@"
}

# Forge TUI - run from anywhere with cwd as workspace
forge() {
  "${script_dir}/forge/forge" "$@"
}

run_aider_local() {
  "${script_dir}/run_aider_local.sh" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  cat <<EOF
To register the 'agent' command in your current shell:
  source "${script_dir}/wrapper_init.sh"

To make it permanent, run:
  ${script_dir}/agent_alias_install.sh

Commands:
  agent                              # Interactive session
  agent -p "Fix bug" file.py         # Inline prompt
  agent -pf task.txt -w ./project    # Prompt from file + workspace
  agent -i screenshot.png -p "Build" # With image (vision)
  agent -s1                          # Use smallest model
  agent --yolo -p "Add tests"        # YOLO mode (auto-yes)
  agent-config                       # Configuration wizard
  agent-model                        # Quick model switch
  agent --help                       # Full options

  forge                              # Forge TUI (uses cwd as workspace)
  forge -p "List files"              # Single prompt mode
  forge -m qwen3:1.7b -p "Create x"  # Specify model
  forge --help                       # Forge options
EOF
fi
