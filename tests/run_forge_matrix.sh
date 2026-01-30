#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

load_dotenv() {
  local file="$1"
  [[ -f "$file" ]] || return
  log "Loading environment defaults from $file"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line//$'\r'/}"
    local trimmed
    trimmed="$(trim "$line")"
    [[ -z "$trimmed" ]] && continue
    [[ "${trimmed:0:1}" == "#" ]] && continue
    if [[ "$trimmed" == export* ]]; then
      trimmed="${trimmed#export }"
      trimmed="$(trim "$trimmed")"
    fi
    [[ "$trimmed" != *=* ]] && continue
    local key="${trimmed%%=*}"
    local value="${trimmed#*=}"
    key="$(trim "$key")"
    value="$(trim "$value")"
    [[ -z "$key" ]] && continue
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done <"$file"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOTENV="${REPO_ROOT}/.env"
load_dotenv "$DOTENV"

export AGENT_CLI_TRACE="${AGENT_CLI_TRACE:-1}"
export AGENT_CLI_DEBUG="${AGENT_CLI_DEBUG:-1}"
export AGENT_CLI_DEBUG_PAYLOAD="${AGENT_CLI_DEBUG_PAYLOAD:-1}"
DEBUG_LOG_FILE="${DEBUG_LOG_FILE:-$REPO_ROOT/logs/forge_trace.log}"
mkdir -p "$(dirname "$DEBUG_LOG_FILE")"
log "Capturing agent payloads to $DEBUG_LOG_FILE"
exec > >(tee -a "$DEBUG_LOG_FILE") 2>&1
PYTHON_CMD="${FORGE_PYTHON:-}"
if [[ -z "$PYTHON_CMD" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
  else
    log "No Python interpreter found; install python or set FORGE_PYTHON."
    exit 1
  fi
fi
log "Using Python interpreter: $PYTHON_CMD"

sort_models_by_size() {
  local raw="$1"
  "$PYTHON_CMD" - "$raw" <<'PY'
import math
import re
import sys

raw = sys.argv[1] if len(sys.argv) > 1 else ""
models = [m.strip() for m in raw.split(",") if m.strip()]

def weight(model: str) -> float:
    suffix = model.split(":", 1)[-1] if ":" in model else model
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)", suffix)
    if match:
        return float(match.group(1))
    return math.inf

models.sort(key=weight)
print(",".join(models))
PY
}

get_timeout_for_model() {
  local model="$1"
  "$PYTHON_CMD" - "$model" <<'PY'
import re
import sys

model = sys.argv[1] if len(sys.argv) > 1 else ""
suffix = model.split(":", 1)[-1] if ":" in model else model
match = re.match(r"([0-9]+(?:\.[0-9]+)?)", suffix)
if match:
    size = float(match.group(1))
    # Small models (< 2B) are slower per token, need longer timeout
    if size < 2:
        print(180)
    # Medium models (2-4B)
    elif size < 4:
        print(120)
    # Larger models (4B+) are faster per token
    else:
        print(90)
else:
    print(120)  # default
PY
}

check_ollama_health() {
  local base_url="${OLLAMA_API_BASE_LOCAL:-http://localhost:11435}"
  local max_attempts=3
  local attempt=0
  while [[ $attempt -lt $max_attempts ]]; do
    if curl -sf "${base_url}/" >/dev/null 2>&1 || \
       curl -sf "${base_url}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    log "Ollama health check failed, attempt $attempt/$max_attempts"
    sleep 2
  done
  return 1
}

MODELS="${FORGE_MODEL_MATRIX:-}"
if [[ -z "$MODELS" ]]; then
  log "FORGE_MODEL_MATRIX is empty. Set it before running."
  exit 1
fi
MODELS="$(sort_models_by_size "$MODELS")"
log "Running models: $MODELS"

WORKSPACE="${FORGE_WORKSPACE:-poc}"
TESTS="${1:-both}" # html | js | both

run_forge() {
  local prompt="$1"
  local model="$2"
  local timeout="${3:-}"
  if [[ -z "$timeout" ]]; then
    timeout="$(get_timeout_for_model "$model")"
  fi
  log "Forge run (model=$model, timeout=${timeout}s)"
  (
    cd "$REPO_ROOT"
    "$PYTHON_CMD" scripts/forge_runner.py \
      --prompt "$prompt" \
      --model "$model" \
      --workspace "$WORKSPACE" \
      --invoke-timeout "$timeout"
  )
}

check_html() {
  local file="$1"
  grep -qi "<!doctype html" "$file" || return 1
  grep -qi "<html" "$file" || return 1
  grep -qi "<head" "$file" || return 1
  grep -qi "<body" "$file" || return 1
  [[ $(grep -i "@keyframes" "$file" | wc -l) -ge 2 ]] || return 1
  [[ $(grep -i "animation" "$file" | wc -l) -ge 2 ]] || return 1
  grep -qi "background" "$file" || return 1
}

check_js_create() {
  local file="$1"
  grep -qi "hello world" "$file" || return 1
  grep -qi "document.body" "$file" || return 1
}

check_js_improve() {
  local file="$1"
  grep -qi "domcontentloaded" "$file" || return 1
  grep -qi "createElement" "$file" || return 1
  grep -qi "append" "$file" || return 1
  grep -qi "console.log" "$file" || return 1
}
IFS=',' read -r -a MODEL_LIST <<< "$MODELS"
MODEL_COUNT=0
for MODEL in "${MODEL_LIST[@]}"; do
  MODEL="$(echo "$MODEL" | xargs)"
  [[ -z "$MODEL" ]] && continue
  SLUG="$(echo "$MODEL" | sed -E 's/[^a-zA-Z0-9_-]+/-/g' | tr '[:upper:]' '[:lower:]')"

  # Health check before each model (with brief pause between models)
  if [[ $MODEL_COUNT -gt 0 ]]; then
    log "Pausing 3s before next model..."
    sleep 3
  fi
  MODEL_COUNT=$((MODEL_COUNT + 1))

  if ! check_ollama_health; then
    log "Ollama unreachable, skipping $MODEL"
    continue
  fi

  TIMEOUT="$(get_timeout_for_model "$MODEL")"
  log "Using timeout=${TIMEOUT}s for $MODEL"

  if [[ "$TESTS" == "html" || "$TESTS" == "both" ]]; then
    HTML_FILE="workspaces/$WORKSPACE/hello-world-$SLUG.html"
    log "=== HTML test for $MODEL ==="
    PROMPT="You are Forge, a system-agnostic coding agent. Create a new file named hello-world-$SLUG.html in the workspace root. The file must be valid HTML5 with <!doctype html>, <html>, <head>, <body>. Include inline CSS and JS, and use vivid, high-contrast colors or gradients for the background and animated elements. Add at least two CSS animations: one for the background and one for text; at least one animation should include a smooth fade effect. Use write_file to create the file; if it already exists, use read_file then apply_patch to update it. Do not create any other files."
    run_forge "$PROMPT" "$MODEL" "$TIMEOUT" || true
    if [[ ! -f "$HTML_FILE" ]]; then
      log "Missing $HTML_FILE; retrying with strict tool-call prompt"
      STRICT="You are Forge. Output ONLY a JSON tool call for write_file with keys {\"name\":\"write_file\",\"arguments\":{\"path\":\"hello-world-$SLUG.html\",\"content\":\"...\"}}. The content must be valid HTML5 with two @keyframes animations, bold colorful gradients for the background and text, and at least one fade animation. Do not include prose."
      run_forge "$STRICT" "$MODEL" "$TIMEOUT" || true
    fi
    if check_html "$HTML_FILE"; then
      log "HTML checks passed: $HTML_FILE"
    else
      log "HTML checks failed; requesting Forge to improve HTML"
      IMPROVE_HTML="You are Forge, a system-agnostic coding agent. Improve the existing file hello-world-$SLUG.html so it has at least two distinct @keyframes animations (background + text) with vibrant colors, at least one fading cycle, and ensure those animations are applied to elements. Use read_file first, then apply_patch. Do not change the filename."
      run_forge "$IMPROVE_HTML" "$MODEL" "$TIMEOUT" || true
      if check_html "$HTML_FILE"; then
        log "HTML checks passed after improve: $HTML_FILE"
      else
        log "HTML checks failed after improve: $HTML_FILE"
        log "Continuing despite failed HTML checks; inspect $HTML_FILE to debug."
        continue
      fi
    fi
  fi

  if [[ "$TESTS" == "js" || "$TESTS" == "both" ]]; then
    JS_FILE="workspaces/$WORKSPACE/function-$SLUG.js"
    log "=== JS test for $MODEL ==="
    CREATE="You are Forge, a system-agnostic coding agent. Create a new file named function-$SLUG.js in the workspace root. The file should only contain JavaScript that displays 'hello world' by setting document.body.textContent and logging to the console. Use write_file to create the file; if it already exists, use read_file then apply_patch to update it. Do not create any other files."
    run_forge "$CREATE" "$MODEL" "$TIMEOUT" || true
    if [[ ! -f "$JS_FILE" ]]; then
      log "Missing $JS_FILE; retrying with strict tool-call prompt"
      STRICT_JS="You are Forge. Output ONLY a JSON tool call for write_file with keys {\"name\":\"write_file\",\"arguments\":{\"path\":\"function-$SLUG.js\",\"content\":\"...\"}}. The content must set document.body text to 'hello world' and log it. Do not include prose."
      run_forge "$STRICT_JS" "$MODEL" "$TIMEOUT" || true
    fi
    if ! check_js_create "$JS_FILE"; then
      log "JS create checks failed: $JS_FILE"
      exit 1
    fi

    IMPROVE="You are Forge, a system-agnostic coding agent. Improve the existing file function-$SLUG.js without changing the filename. Keep the console log and hello world text. Wrap the logic in DOMContentLoaded and avoid overwriting the entire body. Create a dedicated element and append it to the body. Use read_file first, then apply_patch to update the file."
    run_forge "$IMPROVE" "$MODEL" "$TIMEOUT" || true
    if check_js_improve "$JS_FILE"; then
      log "JS improve checks passed: $JS_FILE"
    else
      log "JS improve checks failed: $JS_FILE"
      exit 1
    fi
  fi
done

log "Forge matrix run complete."
