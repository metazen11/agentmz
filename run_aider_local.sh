#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/mnt/c/dropbox/_coding/agentic/v2"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  run_aider_local.sh [--execute] [--set-model MODEL] [--set-ollama-base URL] [aider args...]

Modes:
  (default) Conversation mode (interactive)
  --execute, -execute    Headless run (adds --yes and default --message if missing)

Defaults:
  --timeout 600
  --auto-commits
  --subtree-only (unless --no-git is provided)

Overrides:
  --set-model MODEL         Sets AIDER_MODEL for this run
  --set-ollama-base URL     Sets OLLAMA_API_BASE and OLLAMA_URL for this run

Examples:
  ./run_aider_local.sh
  ./run_aider_local.sh --execute -m "Create a note" notes.txt
  ./run_aider_local.sh --set-model ollama_chat/qwen2.5-coder:3b --execute -m "..." file.txt
  ./run_aider_local.sh --set-ollama-base https://wfhub.localhost/ollama --execute -m "..." file.txt
EOF
  exit 0
fi

cd "$ROOT_DIR"

if [ -f ".env" ]; then
  set -a
  . ".env"
  set +a
  # For local development, use the local Ollama URL (exposed port)
  if [ -n "${OLLAMA_API_BASE_LOCAL:-}" ]; then
    export OLLAMA_API_BASE="$OLLAMA_API_BASE_LOCAL"
    export OLLAMA_URL="$OLLAMA_API_BASE_LOCAL"
  fi
fi

has_model=false
has_subtree_only=false
has_no_git=false
has_timeout=false
has_auto_commits_flag=false
has_yes=false
has_message=false
execute_mode=false
next_is_message=false
override_model=""
override_ollama_base=""
args=()
for arg in "$@"; do
  if [ "$arg" = "-execute" ] || [ "$arg" = "--execute" ]; then
    execute_mode=true
    continue
  elif [ "$arg" = "--set-model" ]; then
    override_model="__next__"
    continue
  elif [[ "$arg" == --set-model=* ]]; then
    override_model="${arg#*=}"
    continue
  elif [ "$arg" = "--set-ollama-base" ]; then
    override_ollama_base="__next__"
    continue
  elif [[ "$arg" == --set-ollama-base=* ]]; then
    override_ollama_base="${arg#*=}"
    continue
  fi
  if [ "$override_model" = "__next__" ]; then
    override_model="$arg"
    continue
  elif [ "$override_ollama_base" = "__next__" ]; then
    override_ollama_base="$arg"
    continue
  fi
  if [ "$arg" = "--model" ]; then
    has_model=true
  elif [ "$arg" = "--subtree-only" ]; then
    has_subtree_only=true
  elif [ "$arg" = "--no-git" ]; then
    has_no_git=true
  elif [ "$arg" = "--timeout" ]; then
    has_timeout=true
  elif [[ "$arg" == --timeout=* ]]; then
    has_timeout=true
  elif [ "$arg" = "--auto-commits" ] || [ "$arg" = "--no-auto-commits" ]; then
    has_auto_commits_flag=true
  elif [ "$arg" = "--yes" ]; then
    has_yes=true
  elif [ "$arg" = "-m" ] || [ "$arg" = "--message" ]; then
    has_message=true
    next_is_message=true
  elif [ "$next_is_message" = true ]; then
    next_is_message=false
  elif [[ "$arg" == --message=* ]]; then
    has_message=true
  fi
  args+=("$arg")
done

set -- "${args[@]}"

if [ -n "$override_model" ]; then
  export AIDER_MODEL="$override_model"
fi
if [ -n "$override_ollama_base" ]; then
  export OLLAMA_API_BASE="$override_ollama_base"
  export OLLAMA_URL="$override_ollama_base"
fi

if [ "$has_model" = false ] && [ -n "${AIDER_MODEL:-}" ]; then
  set -- --model "$AIDER_MODEL" "$@"
fi

if [ "$has_subtree_only" = false ] && [ "$has_no_git" = false ]; then
  set -- --subtree-only "$@"
fi

if [ "$has_timeout" = false ]; then
  set -- --timeout 600 "$@"
fi

if [ "$has_auto_commits_flag" = false ]; then
  set -- --auto-commits "$@"
fi

if [ "$execute_mode" = true ] && [ "$has_yes" = false ]; then
  set -- --yes "$@"
fi

if [ "$execute_mode" = true ] && [ "$has_message" = false ]; then
  set -- --message "Update files for local development." "$@"
fi

exec aider "$@"
