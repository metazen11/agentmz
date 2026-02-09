#!/bin/bash
# v2 Startup Script - Self-contained coding agent stack
# v2 has its own Ollama, DB, and aider-api
#
# Usage:
#   ./start.sh                          # Start with default workspace (poc)
#   ./start.sh --workspace beatbridge   # Start with specific workspace
#   ./start.sh -w poc                   # Short form
#   ./start.sh --no-browser             # Don't open browser at end

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# === Parse CLI Arguments ===
WORKSPACE=""
NO_BROWSER=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --workspace|-w)
            WORKSPACE="$2"
            shift 2
            ;;
        --no-browser)
            NO_BROWSER=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./start.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -w, --workspace NAME   Set the default workspace (e.g., poc, beatbridge_app)"
            echo "  --no-browser           Don't open browser at end"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Workspaces are located in: $SCRIPT_DIR/workspaces/"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "=== v2 Coding Agent Stack ==="
echo ""

# Load environment without eval (handles regex values safely)
if [ -f .env ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|\#*) continue ;;
        esac
        if [[ "$line" == *"="* ]]; then
            key="${line%%=*}"
            value="${line#*=}"
            key="${key#"${key%%[![:space:]]*}"}"
            key="${key%"${key##*[![:space:]]}"}"
            value="${value#"${value%%[![:space:]]*}"}"
            value="${value%"${value##*[![:space:]]}"}"
            export "${key}=${value}"
        fi
    done < .env
fi

# Override DEFAULT_WORKSPACE if specified via CLI
if [ -n "$WORKSPACE" ]; then
    # Validate workspace exists
    if [ ! -d "$SCRIPT_DIR/workspaces/$WORKSPACE" ]; then
        echo "ERROR: Workspace not found: $SCRIPT_DIR/workspaces/$WORKSPACE"
        echo ""
        echo "Available workspaces:"
        ls -1 "$SCRIPT_DIR/workspaces/" 2>/dev/null | sed 's/^/  - /'
        exit 1
    fi
    export DEFAULT_WORKSPACE="$WORKSPACE"
    echo "Workspace: $WORKSPACE (from CLI)"
else
    echo "Workspace: ${DEFAULT_WORKSPACE:-poc} (from .env or default)"
fi
echo ""

AGENT_MODEL="${AGENT_MODEL:-qwen3:1.7b}"
VISION_MODEL="${VISION_MODEL:-qwen2.5vl:7b}"
AIDER_API_PORT="${AIDER_API_PORT:-8001}"
V2_OLLAMA_PORT="11435"  # v2 Ollama exposed on different port

# Startup automation defaults (can be overridden via .env)
AUTO_PULL_ENABLE="${AUTO_PULL_ENABLE:-1}"
AUTO_PULL_MODELS="${AUTO_PULL_MODELS:-gemma3:4b,qwen3:0.6b,qwen2.5-coder:3b}"
AUTO_PULL_MIN_FREE_GB="${AUTO_PULL_MIN_FREE_GB:-15}"
VRAM_DETECT="${VRAM_DETECT:-1}"
VRAM_FALLBACK_GB="${VRAM_FALLBACK_GB:-4}"
VRAM_Q4_THRESHOLD_GB="${VRAM_Q4_THRESHOLD_GB:-4}"
OLLAMA_MAX_VRAM_DYNAMIC="${OLLAMA_MAX_VRAM_DYNAMIC:-1}"

# === Check and Start Docker ===
start_docker_desktop() {
    echo "Docker is not running. Attempting to start Docker Desktop..."

    # Detect OS
    case "$(uname -s)" in
        Darwin)
            # macOS
            if [ -d "/Applications/Docker.app" ]; then
                echo "Starting Docker Desktop (macOS)..."
                open -a Docker
                return 0
            fi
            ;;
        Linux)
            # Check if WSL (Windows Subsystem for Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                # WSL - try Windows Docker Desktop paths
                DOCKER_DESKTOP_PATHS=(
                    "/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe"
                    "/mnt/c/Program Files (x86)/Docker/Docker/Docker Desktop.exe"
                )

                for docker_path in "${DOCKER_DESKTOP_PATHS[@]}"; do
                    if [ -f "$docker_path" ]; then
                        echo "Starting Docker Desktop (Windows/WSL)..."
                        "$docker_path" &
                        return 0
                    fi
                done

                # Try via cmd.exe as fallback
                if command -v cmd.exe &> /dev/null; then
                    echo "Starting Docker Desktop via cmd.exe..."
                    cmd.exe /c "start \"\" \"C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe\"" 2>/dev/null &
                    return 0
                fi
            else
                # Native Linux - try systemctl
                if command -v systemctl &> /dev/null; then
                    echo "Starting Docker service (Linux)..."
                    sudo systemctl start docker 2>/dev/null && return 0
                fi
            fi
            ;;
    esac

    return 1
}

wait_for_docker() {
    local max_wait=60
    echo -n "Waiting for Docker to be ready... "
    for i in $(seq 1 $max_wait); do
        if docker info > /dev/null 2>&1; then
            echo "ready (${i}s)"
            return 0
        fi
        sleep 1
    done
    echo "timeout after ${max_wait}s"
    return 1
}

if ! docker info > /dev/null 2>&1; then
    docker_err=$(docker info 2>&1 || true)
    if echo "$docker_err" | grep -qi "permission denied while trying to connect to the docker api"; then
        echo "ERROR: Docker is running but your user lacks permission to access the Docker socket."
        echo ""
        echo "Fix:"
        echo "  1) sudo usermod -aG docker \$USER"
        echo "  2) newgrp docker   # or log out/in to refresh group membership"
        echo "  3) rerun ./start.sh"
        exit 1
    fi

    if start_docker_desktop; then
        if ! wait_for_docker; then
            echo "ERROR: Docker Desktop started but not responding."
            echo "Please ensure Docker Desktop is fully started and try again."
            exit 1
        fi
    else
        echo "ERROR: Could not start Docker Desktop automatically."
        echo "Please start Docker Desktop manually and try again."
        exit 1
    fi
fi
echo "Docker: running"

# === VRAM Detection (for Ollama config) ===
detect_vram_gb() {
    if [ "$VRAM_DETECT" != "1" ]; then
        echo "$VRAM_FALLBACK_GB"
        return 0
    fi
    if command -v nvidia-smi >/dev/null 2>&1; then
        local vram_mb
        vram_mb="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d ' ')"
        if [[ "$vram_mb" =~ ^[0-9]+$ ]] && [ "$vram_mb" -gt 0 ]; then
            echo $((vram_mb / 1024))
            return 0
        fi
    fi
    echo "$VRAM_FALLBACK_GB"
}

get_free_gb() {
    if command -v df >/dev/null 2>&1; then
        local path="/var/lib/docker"
        if [ -d "$path" ]; then
            df -BG --output=avail "$path" 2>/dev/null | tail -n 1 | tr -dc '0-9'
            return 0
        fi
    fi
    echo ""
}

if [ "$OLLAMA_MAX_VRAM_DYNAMIC" = "1" ]; then
    VRAM_GB="$(detect_vram_gb)"
    if [[ "$VRAM_GB" =~ ^[0-9]+$ ]] && [ "$VRAM_GB" -gt 0 ]; then
        export OLLAMA_MAX_VRAM=$((VRAM_GB * 1024 * 1024 * 1024))
        echo "Detected VRAM: ${VRAM_GB}GB (setting OLLAMA_MAX_VRAM=${OLLAMA_MAX_VRAM})"
    fi
fi

# === Start v2 Services ===
echo "--- Starting v2 Services ---"
docker compose --env-file .env -f docker/docker-compose.yml up -d

# === Wait for v2 Ollama ===
echo ""
echo "--- v2 Ollama Setup ---"
echo -n "Waiting for v2 Ollama... "
for i in {1..60}; do
    if curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
        echo "ready"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "timeout"
        echo "Check logs: docker logs wfhub-v2-ollama"
        exit 1
    fi
    sleep 1
done

# Check if required models are available, pull if not
AVAILABLE_MODELS=$(curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" 2>/dev/null || echo '{"models":[]}')

ensure_model() {
    local model="$1"
    local label="$2"

    if [ -z "$model" ]; then
        return 0
    fi

    echo -n "Checking model ($label: $model)... "
    if echo "$AVAILABLE_MODELS" | grep -q "\"name\":\"$model\""; then
        echo "OK"
    else
        echo "NOT FOUND"
        local free_gb
        free_gb="$(get_free_gb)"
        if [[ "$free_gb" =~ ^[0-9]+$ ]] && [ "$free_gb" -lt "$AUTO_PULL_MIN_FREE_GB" ]; then
            echo ""
            echo "Skipping pull for $model: low disk space (${free_gb}GB free, requires >= ${AUTO_PULL_MIN_FREE_GB}GB)."
            return 0
        fi
        echo ""
        echo "Pulling model $model into v2 Ollama..."
        docker exec wfhub-v2-ollama ollama pull "$model"
        echo "Model ready"
        AVAILABLE_MODELS=$(curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" 2>/dev/null || echo '{"models":[]}')
    fi
}

dedupe_models() {
    local input="$1"
    local output=""
    declare -A seen
    IFS=',' read -r -a items <<< "$input"
    for item in "${items[@]}"; do
        item="$(echo "$item" | xargs)"
        [ -z "$item" ] && continue
        if [ -z "${seen[$item]:-}" ]; then
            seen[$item]=1
            if [ -z "$output" ]; then
                output="$item"
            else
                output="${output},${item}"
            fi
        fi
    done
    echo "$output"
}

select_model_variant() {
    local model="$1"
    local vram_gb="$2"
    if echo "$model" | grep -qi -- '-q[0-9]'; then
        echo "$model"
        return 0
    fi
    if [[ "$vram_gb" =~ ^[0-9]+$ ]] && [ "$vram_gb" -le "$VRAM_Q4_THRESHOLD_GB" ]; then
        case "$model" in
            qwen3:0.6b) echo "qwen3:0.6b-q4_K_M"; return 0 ;;
        esac
    fi
    echo "$model"
}

ensure_model "$AGENT_MODEL" "agent"
if [ "$VISION_MODEL" != "$AGENT_MODEL" ]; then
    ensure_model "$VISION_MODEL" "vision"
fi

if [ "$AUTO_PULL_ENABLE" = "1" ] && [ -n "$AUTO_PULL_MODELS" ]; then
    VRAM_GB="${VRAM_GB:-$(detect_vram_gb)}"
    AUTO_PULL_MODELS="$(dedupe_models "$AUTO_PULL_MODELS")"
    echo ""
    echo "Auto-pull models: $AUTO_PULL_MODELS"
    IFS=',' read -r -a AUTO_MODELS <<< "$AUTO_PULL_MODELS"
    for model in "${AUTO_MODELS[@]}"; do
        model="$(echo "$model" | xargs)"
        [ -z "$model" ] && continue
        selected="$(select_model_variant "$model" "$VRAM_GB")"
        ensure_model "$selected" "auto"
    done
fi

# Show v2 Ollama models
echo ""
echo "v2 Ollama models:"
curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" | python3 -c "import json,sys; data=json.load(sys.stdin); [print(f'  - {m[\"name\"]}') for m in data.get('models',[])]" 2>/dev/null || echo "  (none yet)"

# === Run Database Migrations ===
echo ""
echo "--- Database Migrations ---"
echo -n "Running Alembic migrations... "
set +e
migration_output=$(docker exec wfhub-v2-main-api alembic upgrade head 2>&1)
migration_exit=$?
set -e

if [ $migration_exit -eq 0 ]; then
    echo "done"
else
    echo "failed (checking status...)"
fi

if [ -n "$migration_output" ]; then
    echo "Migration output:"
    echo "$migration_output" | sed 's/^/  /'
fi

if [ $migration_exit -ne 0 ]; then
    docker exec wfhub-v2-main-api alembic current 2>&1 | head -5
fi

# === Wait for Aider API ===
echo ""
echo "--- Aider API ---"
echo -n "Waiting for Aider API... "
for i in {1..30}; do
    if curl -sf "http://localhost:${AIDER_API_PORT}/health" > /dev/null 2>&1; then
        echo "ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "timeout"
        echo "Check logs: docker logs wfhub-v2-aider-api"
        exit 1
    fi
    sleep 1
done

# === Status ===
echo ""
echo "=== v2 Stack Status ==="
docker compose --env-file .env -f docker/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== Config ==="
curl -s "http://localhost:${AIDER_API_PORT}/health" | python3 -m json.tool 2>/dev/null || true

echo ""
echo "=== Quick Test ==="
echo "  # Health check"
echo "  curl http://localhost:${AIDER_API_PORT}/health"
echo ""
echo "  # Run POC game tests"
echo "  pytest tests/test_poc_game.py -v -s"
echo ""

# === Open Browser ===
if [ "$NO_BROWSER" = false ]; then
    open_browser() {
        local url="$1"
        case "$(uname -s)" in
            Darwin)
                open "$url"
                return 0
                ;;
            Linux)
                if grep -qi microsoft /proc/version 2>/dev/null; then
                    # WSL - use Windows browser
                    if command -v cmd.exe &> /dev/null; then
                        cmd.exe /c start "$url" 2>/dev/null &
                        return 0
                    elif command -v powershell.exe &> /dev/null; then
                        powershell.exe -c "Start-Process '$url'" 2>/dev/null &
                        return 0
                    fi
                else
                    # Native Linux
                    if command -v xdg-open &> /dev/null; then
                        xdg-open "$url" 2>/dev/null &
                        return 0
                    fi
                fi
                ;;
        esac
        return 1
    }

    echo "Opening browser..."
    open_browser "https://wfhub.localhost" || open_browser "http://localhost:8002"
fi

# === Install Agent Alias (non-blocking, skip if already installed) ===
echo ""
echo "--- Agent Setup ---"
if [ -n "${AGENTMZ_DIR:-}" ] && command -v aider &> /dev/null; then
    echo "agent: already configured (AGENTMZ_DIR=$AGENTMZ_DIR)"
elif [ -f "$SCRIPT_DIR/agent_alias_install.sh" ]; then
    ("$SCRIPT_DIR/agent_alias_install.sh") || echo "  (agent setup skipped - run ./agent_alias_install.sh manually)"
fi

# === Check for VS Code ===
if ! command -v code &> /dev/null; then
    echo ""
    echo "--- VS Code Not Found ---"
    if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "WSL detected - install VS Code on Windows:"
        echo "  winget install Microsoft.VisualStudioCode"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Install VS Code on macOS:"
        echo "  brew install --cask visual-studio-code"
    else
        echo "Install VS Code on Linux:"
        echo "  sudo snap install code --classic"
    fi
fi

# === Start File Opener Service (for opening files in editor) ===
echo ""
echo "--- File Opener ---"
FILE_OPENER_PID=$(lsof -ti:8888 2>/dev/null)
if [ -n "$FILE_OPENER_PID" ]; then
    echo "file-opener: already running (pid $FILE_OPENER_PID)"
else
    if [ -f "$SCRIPT_DIR/scripts/file-opener.py" ]; then
        nohup python3 "$SCRIPT_DIR/scripts/file-opener.py" > /tmp/file-opener.log 2>&1 &
        echo "file-opener: started on http://localhost:8888"
    else
        echo "file-opener: script not found (clicking files will copy path instead)"
    fi
fi

echo ""
echo "Ready!"
