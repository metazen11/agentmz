#!/usr/bin/env bash
set -uo pipefail
# Note: removed -e to prevent exit on error; we handle failures gracefully

FAILED_TESTS=()

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
export AGENT_CLI_LOG_RESPONSES="${AGENT_CLI_LOG_RESPONSES:-1}"
export AGENT_CLI_LOG_DIR="${AGENT_CLI_LOG_DIR:-$REPO_ROOT/logs}"
export AGENT_CLI_SPINNER="${AGENT_CLI_SPINNER:-1}"
export AGENT_CLI_MAX_ITERS="${AGENT_CLI_MAX_ITERS:-2}"
export AGENT_CLI_TOOL_FALLBACK="${AGENT_CLI_TOOL_FALLBACK:-1}"  # Parse JSON from text when model doesn't use native tool calls
DEBUG_LOG_FILE="${DEBUG_LOG_FILE:-$REPO_ROOT/logs/forge_trace.log}"
mkdir -p "$(dirname "$DEBUG_LOG_FILE")"
log "Capturing agent payloads to $DEBUG_LOG_FILE"
exec > >(tee -a "$DEBUG_LOG_FILE") 2>&1
# Auto-detect Python with venv preference
PYTHON_CMD="${FORGE_PYTHON:-}"
if [[ -z "$PYTHON_CMD" ]]; then
  # Prefer venv python (has langchain-ollama installed)
  if [[ -f "$REPO_ROOT/venv/bin/python3" ]]; then
    PYTHON_CMD="$REPO_ROOT/venv/bin/python3"
  elif [[ -f "$REPO_ROOT/venv/bin/python" ]]; then
    PYTHON_CMD="$REPO_ROOT/venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
  else
    log "ERROR: No Python interpreter found; install python or set FORGE_PYTHON."
    log "Exiting gracefully."
    return 1 2>/dev/null || exit 1
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

discover_pulled_models() {
  local base_url="${OLLAMA_API_BASE_LOCAL:-http://localhost:11435}"
  curl -sf "${base_url}/api/tags" 2>/dev/null | "$PYTHON_CMD" -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = [m['name'] for m in data.get('models', [])]
    print(','.join(models))
except:
    pass
"
}

# Use FORGE_MODEL_MATRIX if set, otherwise auto-discover from Ollama
MODELS="${FORGE_MODEL_MATRIX:-}"
if [[ -z "$MODELS" ]]; then
  log "FORGE_MODEL_MATRIX not set, auto-discovering pulled models..."
  MODELS="$(discover_pulled_models)"
  if [[ -z "$MODELS" ]]; then
    log "ERROR: No models found in Ollama. Pull some models first."
    log "Example: ollama pull qwen3:0.6b"
    log "Exiting gracefully."
    return 1 2>/dev/null || exit 1
  fi
  log "Discovered models: $MODELS"
fi
MODELS="$(sort_models_by_size "$MODELS")"
log "Running models (sorted by size): $MODELS"

WORKSPACE="${FORGE_WORKSPACE:-poc}"
TESTS="${1:-both}" # html | py | both

run_forge() {
  local prompt="$1"
  local model="$2"
  local invoke_timeout="${3:-}"
  if [[ -z "$invoke_timeout" ]]; then
    invoke_timeout="$(get_timeout_for_model "$model")"
  fi
  # Process-level timeout as safeguard (2x invoke timeout for retries)
  local process_timeout=$((invoke_timeout * 3))
  log "Forge run (model=$model, invoke_timeout=${invoke_timeout}s, process_timeout=${process_timeout}s)"
  (
    cd "$REPO_ROOT"
    timeout --kill-after=10 "${process_timeout}s" \
      "$PYTHON_CMD" scripts/forge_runner.py \
        --prompt "$prompt" \
        --model "$model" \
        --workspace "$WORKSPACE" \
        --invoke-timeout "$invoke_timeout"
  )
}

cleanup_test_files() {
  local workspace="$1"
  local slug="$2"
  log "Cleaning up previous test files for $slug..."
  rm -f "workspaces/$workspace/hello-world-$slug.html" 2>/dev/null || true
  rm -f "workspaces/$workspace/converter-$slug.py" 2>/dev/null || true
}

check_html() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  grep -qi "<!doctype html" "$file" || return 1
  grep -qi "<html" "$file" || return 1
  grep -qi "<head" "$file" || return 1
  grep -qi "<body" "$file" || return 1
  [[ $(grep -i "@keyframes" "$file" | wc -l) -ge 2 ]] || return 1
  [[ $(grep -i "animation" "$file" | wc -l) -ge 2 ]] || return 1
  grep -qi "infinite" "$file" || return 1  # Must loop infinitely
  grep -qi "background" "$file" || return 1
}

check_converter_create() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  # Must have shebang and be valid Python structure
  grep -q "#!/usr/bin/env python" "$file" || grep -q "^import\|^from" "$file" || return 1
  # Must use argparse for CLI
  grep -qi "argparse\|ArgumentParser" "$file" || return 1
  # Must handle JSON and CSV
  grep -qi "json" "$file" || return 1
  grep -qi "csv" "$file" || return 1
  # Must have main entry point
  grep -qi "__main__\|def main" "$file" || return 1
}

check_converter_improve() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  # Check for improvement comment
  grep -qi "IMPROVED" "$file" || return 1
  # Check for error handling with specific exceptions
  grep -qi "FileNotFoundError\|JSONDecodeError" "$file" || return 1
  # Check for extracted function (testable code)
  grep -qi "def convert" "$file" || return 1
  # Check for input validation (file exists check)
  grep -qi "exists\|isfile\|os.path" "$file" || return 1
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

  # Clean up previous test files to avoid "file already exists" errors
  cleanup_test_files "$WORKSPACE" "$SLUG"

  TIMEOUT="$(get_timeout_for_model "$MODEL")"
  log "Using timeout=${TIMEOUT}s for $MODEL"

  if [[ "$TESTS" == "html" || "$TESTS" == "both" ]]; then
    HTML_FILE="workspaces/$WORKSPACE/hello-world-$SLUG.html"
    log "=== HTML test for $MODEL ==="
    PROMPT="Create hello-world-$SLUG.html with valid HTML5 structure. Include inline CSS/JS with vibrant colors. Add two @keyframes animations with 'infinite': one for background, one for text fade. Use write_file."
    run_forge "$PROMPT" "$MODEL" "$TIMEOUT" || true
    if [[ ! -f "$HTML_FILE" ]]; then
      log "Missing $HTML_FILE; retrying with strict tool-call prompt"
      STRICT="Output ONLY JSON: {\"name\":\"write_file\",\"arguments\":{\"path\":\"hello-world-$SLUG.html\",\"content\":\"...\"}}. HTML5 with two @keyframes infinite animations, gradients, fade. No prose."
      run_forge "$STRICT" "$MODEL" "$TIMEOUT" || true
    fi
    if check_html "$HTML_FILE"; then
      log "HTML checks passed: $HTML_FILE"
    else
      log "HTML checks failed; requesting Forge to improve HTML"
      IMPROVE_HTML="Fix hello-world-$SLUG.html: read_file then apply_patch. Ensure: two @keyframes with 'infinite', gradient background. Add '<!-- IMPROVED -->' comment."
      run_forge "$IMPROVE_HTML" "$MODEL" "$TIMEOUT" || true
      if check_html "$HTML_FILE"; then
        log "HTML checks passed after improve: $HTML_FILE"
      else
        log "HTML checks failed after improve: $HTML_FILE"
        FAILED_TESTS+=("$MODEL:html")
        log "HTML checks failed; inspect $HTML_FILE to debug. Continuing to Python test..."
      fi
    fi
  fi

  if [[ "$TESTS" == "py" || "$TESTS" == "both" ]]; then
    PY_FILE="workspaces/$WORKSPACE/converter-$SLUG.py"
    log "=== Python Converter test for $MODEL ==="
    CREATE="Create converter-$SLUG.py: JSON to CSV CLI using argparse (--input, --output), stdlib only (json, csv), __main__ block, success message. Use write_file."
    run_forge "$CREATE" "$MODEL" "$TIMEOUT" || true
    if [[ ! -f "$PY_FILE" ]]; then
      log "Missing $PY_FILE; retrying with strict tool-call prompt"
      STRICT_PY="Output ONLY JSON: {\"name\":\"write_file\",\"arguments\":{\"path\":\"converter-$SLUG.py\",\"content\":\"...\"}}. Python: argparse, json, csv, __main__. No prose."
      run_forge "$STRICT_PY" "$MODEL" "$TIMEOUT" || true
    fi
    if ! check_converter_create "$PY_FILE"; then
      log "Python converter create checks failed: $PY_FILE"
      FAILED_TESTS+=("$MODEL:converter_create")
      continue
    fi

    IMPROVE="Improve converter-$SLUG.py: read_file then apply_patch. Fix: snake_case names, try/except FileNotFoundError+JSONDecodeError, input validation, extract convert_json_to_csv() function. Add '# IMPROVED' comment."
    run_forge "$IMPROVE" "$MODEL" "$TIMEOUT" || true
    if check_converter_improve "$PY_FILE"; then
      log "Python converter improve checks passed: $PY_FILE"
    else
      log "Python converter improve checks failed: $PY_FILE"
      FAILED_TESTS+=("$MODEL:converter_improve")
    fi
  fi
done

log "Forge matrix run complete."

# Report summary
if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
  log "========================================="
  log "FAILED TESTS (${#FAILED_TESTS[@]}):"
  for test in "${FAILED_TESTS[@]}"; do
    log "  - $test"
  done
  log "========================================="
  log "Some tests failed. Review logs above for details."
else
  log "All tests passed!"
fi
