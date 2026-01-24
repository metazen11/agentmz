#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/mnt/c/dropbox/_coding/agentmz"

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
fi
check_ollama_base() {
  local base="$1"
  if [ -z "$base" ]; then
    return 1
  fi
  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi
  local url="${base%/}/api/tags"
  if [[ "$base" == https://* ]]; then
    curl -fsSk --max-time 2 "$url" >/dev/null 2>&1
  else
    curl -fsS --max-time 2 "$url" >/dev/null 2>&1
  fi
}

resolve_ollama_base() {
  local candidates=()
  if [ -n "${override_ollama_base:-}" ]; then
    candidates+=("$override_ollama_base")
  fi
  if [ -n "${OLLAMA_API_BASE_LOCAL:-}" ]; then
    candidates+=("$OLLAMA_API_BASE_LOCAL")
  fi
  if [ -n "${OLLAMA_API_BASE:-}" ]; then
    candidates+=("$OLLAMA_API_BASE")
  fi
  candidates+=("http://localhost:8002/ollama" "http://localhost:11435" "https://wfhub.localhost/ollama" "http://localhost:11434")

  for base in "${candidates[@]}"; do
    if check_ollama_base "$base"; then
      echo "$base"
      return 0
    fi
  done

  for base in "${candidates[@]}"; do
    if [ -n "$base" ]; then
      echo "$base"
      return 0
    fi
  done
  return 1
}

list_ollama_models() {
  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  local url="${OLLAMA_API_BASE%/}/api/tags"
  local payload=""
  if [[ "${OLLAMA_API_BASE:-}" == https://* ]]; then
    payload="$(curl -fsSk --max-time 2 "$url" 2>/dev/null || true)"
  else
    payload="$(curl -fsS --max-time 2 "$url" 2>/dev/null || true)"
  fi
  if [ -z "$payload" ]; then
    return 0
  fi
  printf '%s' "$payload" | python3 - <<'PY' 2>/dev/null || true
import json,sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for model in data.get("models", []):
    name = model.get("name")
    if name:
        print(name)
PY
}

model_exists() {
  local model="$1"
  if [ -z "$model" ]; then
    return 1
  fi
  printf '%s\n' "$AVAILABLE_MODELS" | grep -Fx "$model" >/dev/null 2>&1
}

normalize_model_name() {
  local model="$1"
  if [ -z "$model" ]; then
    echo ""
    return
  fi
  if [[ "$model" == ollama_chat/* ]]; then
    echo "${model#ollama_chat/}"
    return
  fi
  echo "$model"
}

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

resolved_base="$(resolve_ollama_base || true)"
if [ -n "$resolved_base" ]; then
  export OLLAMA_API_BASE="$resolved_base"
  export OLLAMA_URL="$resolved_base"
fi

if [ -n "$override_ollama_base" ] && [ -n "$resolved_base" ] && [ "$override_ollama_base" != "$resolved_base" ]; then
  echo "Warning: override Ollama base unreachable; using $resolved_base" >&2
fi

if [ -n "${OLLAMA_API_BASE:-}" ]; then
  echo "Using OLLAMA_API_BASE=$OLLAMA_API_BASE"
fi

if [ -n "$override_model" ]; then
  export AIDER_MODEL="$override_model"
fi

AVAILABLE_MODELS="$(list_ollama_models)"
if [ "$has_model" = false ] && [ -z "$override_model" ]; then
  requested_model="${AIDER_MODEL:-}"
  fallback_model="${AGENT_MODEL:-}"
  requested_base="$(normalize_model_name "$requested_model")"
  fallback_base="$(normalize_model_name "$fallback_model")"

  if [ -n "$requested_base" ] && model_exists "$requested_base"; then
    export AIDER_MODEL="ollama_chat/$requested_base"
  elif [ -n "$fallback_base" ] && model_exists "$fallback_base"; then
    export AIDER_MODEL="ollama_chat/$fallback_base"
  elif model_exists "qwen3:1.7b"; then
    export AIDER_MODEL="ollama_chat/qwen3:1.7b"
  elif [ -n "$AVAILABLE_MODELS" ]; then
    first_model="$(printf '%s\n' "$AVAILABLE_MODELS" | head -n 1)"
    export AIDER_MODEL="ollama_chat/$first_model"
  fi
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
