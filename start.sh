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

# Load environment
if [ -f .env ]; then
    source .env
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
AIDER_API_PORT="${AIDER_API_PORT:-8001}"
V2_OLLAMA_PORT="11435"  # v2 Ollama exposed on different port

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

# Check if required model is available, pull if not
echo -n "Checking model ($AGENT_MODEL)... "
AVAILABLE_MODELS=$(curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" 2>/dev/null || echo '{"models":[]}')

if echo "$AVAILABLE_MODELS" | grep -q "\"name\":\"$AGENT_MODEL\""; then
    echo "OK"
else
    echo "NOT FOUND"
    echo ""
    echo "Pulling model $AGENT_MODEL into v2 Ollama..."
    docker exec wfhub-v2-ollama ollama pull "$AGENT_MODEL"
    echo "Model ready"
fi

# Show v2 Ollama models
echo ""
echo "v2 Ollama models:"
curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" | python3 -c "import json,sys; data=json.load(sys.stdin); [print(f'  - {m[\"name\"]}') for m in data.get('models',[])]" 2>/dev/null || echo "  (none yet)"

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

echo "Ready!"
