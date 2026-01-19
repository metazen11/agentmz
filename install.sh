#!/bin/bash
# Workflow Hub v2 - Unified Installer
# One-command setup: venv, deps, Docker services, migrations, models, browser
#
# Usage:
#   ./install.sh                    # Full installation
#   ./install.sh --skip-models      # Skip Ollama model pulling
#   ./install.sh --skip-https       # Skip local HTTPS trust step
#   ./install.sh --no-browser       # Don't open browser at end
#   ./install.sh --help             # Show help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
SKIP_MODELS=false
SKIP_HTTPS=false
NO_BROWSER=false

# === Parse CLI Arguments ===
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-models)
            SKIP_MODELS=true
            shift
            ;;
        --skip-https)
            SKIP_HTTPS=true
            shift
            ;;
        --no-browser)
            NO_BROWSER=true
            shift
            ;;
        --help|-h)
            echo "Workflow Hub v2 - Unified Installer"
            echo ""
            echo "Usage: ./install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-models    Skip Ollama model pulling"
            echo "  --skip-https     Skip local HTTPS trust step"
            echo "  --no-browser     Don't open browser at end"
            echo "  -h, --help       Show this help message"
            echo ""
            echo "After installation:"
            echo "  - Access UI at https://wfhub.localhost"
            echo "  - Start services: ./start.sh"
            echo "  - Run tests: pytest tests/ -v"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo ""
echo -e "${BLUE}=== Workflow Hub v2 Installer ===${NC}"
echo ""

# === Step 1: Check Prerequisites ===
echo -e "${YELLOW}[1/11] Checking prerequisites...${NC}"

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python 3 not found. Please install Python 3.10+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ]]; then
    echo -e "${RED}ERROR: Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "  Python: ${GREEN}$PYTHON_VERSION${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not found. Please install Docker Desktop.${NC}"
    exit 1
fi
echo -e "  Docker: ${GREEN}installed${NC}"

# Check Docker Compose (v2 syntax)
if ! docker compose version &> /dev/null; then
    echo -e "${RED}ERROR: Docker Compose v2 not found.${NC}"
    echo "Please update Docker Desktop or install docker-compose-plugin"
    exit 1
fi
echo -e "  Docker Compose: ${GREEN}available${NC}"

# === Step 2: Start Docker if needed ===
echo -e "${YELLOW}[2/11] Ensuring Docker is running...${NC}"

start_docker_desktop() {
    case "$(uname -s)" in
        Darwin)
            if [ -d "/Applications/Docker.app" ]; then
                open -a Docker
                return 0
            fi
            ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                # WSL
                if command -v cmd.exe &> /dev/null; then
                    cmd.exe /c "start \"\" \"C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe\"" 2>/dev/null &
                    return 0
                fi
            else
                if command -v systemctl &> /dev/null; then
                    sudo systemctl start docker 2>/dev/null && return 0
                fi
            fi
            ;;
    esac
    return 1
}

if ! docker info > /dev/null 2>&1; then
    echo "  Docker not running, attempting to start..."
    if start_docker_desktop; then
        echo -n "  Waiting for Docker... "
        for i in $(seq 1 60); do
            if docker info > /dev/null 2>&1; then
                echo -e "${GREEN}ready${NC}"
                break
            fi
            if [ $i -eq 60 ]; then
                echo -e "${RED}timeout${NC}"
                echo "Please start Docker Desktop manually and try again."
                exit 1
            fi
            sleep 1
        done
    else
        echo -e "${RED}ERROR: Could not start Docker. Please start Docker Desktop manually.${NC}"
        exit 1
    fi
else
    echo -e "  Docker: ${GREEN}running${NC}"
fi

# === Step 3: Create Virtual Environment ===
echo -e "${YELLOW}[3/11] Setting up Python virtual environment...${NC}"

if [ ! -d "venv" ]; then
    echo "  Creating venv..."
    python3 -m venv venv
else
    echo "  venv already exists"
fi

source venv/bin/activate
echo -e "  Activated: ${GREEN}venv${NC}"

# === Step 4: Install Python Dependencies ===
echo -e "${YELLOW}[4/11] Installing Python dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo -e "  Dependencies: ${GREEN}installed${NC}"

# === Step 5: Install Playwright Browsers ===
echo -e "${YELLOW}[5/11] Installing Playwright browsers...${NC}"
python3 -m playwright install chromium --quiet 2>/dev/null || python3 -m playwright install chromium
echo -e "  Playwright: ${GREEN}chromium installed${NC}"

# === Step 6: Create .env if missing ===
echo -e "${YELLOW}[6/11] Checking configuration...${NC}"

if [ ! -f ".env" ]; then
    echo "  Creating .env with defaults..."
    cat > .env << 'EOF'
# Workflow Hub v2 Configuration
# Generated by install.sh

# Database
DATABASE_URL=postgresql://wfhub:wfhub@localhost:5433/agentic
POSTGRES_USER=wfhub
POSTGRES_PASSWORD=wfhub
POSTGRES_DB=agentic

# Ollama LLM
OLLAMA_URL=http://localhost:11435
OLLAMA_API_BASE=http://localhost:11435

# Aider Configuration (for code edits)
AIDER_MODEL=ollama_chat/qwen3:1.7b
AIDER_API_URL=http://localhost:8001

# Agent Configuration (for orchestration)
AGENT_MODEL=qwen3:1.7b
AGENT_TIMEOUT=120
MAX_ITERATIONS=20

# Ports
FASTAPI_PORT=8002
AIDER_API_PORT=8001

# Workspaces
WORKSPACES_DIR=workspaces
DEFAULT_WORKSPACE=poc

# Project root for self-editing (dogfooding)
PROJECT_ROOT=/mnt/c/dropbox/_coding/agentic/v2

# Git identity (for aider workspace repos)
GIT_USER_NAME=Metazen11
GIT_USER_EMAIL=metazen@artofmetazen.com
EOF
    echo -e "  .env: ${GREEN}created${NC}"
else
    echo -e "  .env: ${GREEN}exists${NC}"
fi

source .env

# === Step 7: Start Docker Services ===
echo -e "${YELLOW}[7/11] Starting Docker services...${NC}"
docker compose --env-file .env -f docker/docker-compose.yml up -d
echo -e "  Services: ${GREEN}started${NC}"

# === Step 8: Configure HTTPS ===
echo -e "${YELLOW}[8/11] Configuring local HTTPS...${NC}"
if [ "$SKIP_HTTPS" = false ]; then
    echo -n "  Caddy... "
    for i in $(seq 1 30); do
        if docker ps --format '{{.Names}}' | grep -q "^wfhub-v2-caddy$"; then
            echo -e "${GREEN}running${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${YELLOW}not running${NC}"
        fi
        sleep 1
    done
    echo "  Trusting Caddy local CA (may prompt for sudo)..."
    if ./scripts/trust_caddy_ca.sh; then
        echo -e "  HTTPS: ${GREEN}trusted${NC}"
    else
        echo -e "  HTTPS: ${YELLOW}manual trust required${NC}"
    fi
else
    echo -e "  HTTPS: ${YELLOW}skipped (--skip-https)${NC}"
fi

# === Step 9: Wait for Services ===
echo -e "${YELLOW}[9/11] Waiting for services to be healthy...${NC}"

# Wait for PostgreSQL
echo -n "  PostgreSQL... "
for i in $(seq 1 30); do
    if docker exec wfhub-v2-db pg_isready -U wfhub > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}timeout${NC}"
        echo "Check logs: docker logs wfhub-v2-db"
        exit 1
    fi
    sleep 1
done

# Wait for Ollama
V2_OLLAMA_PORT="${V2_OLLAMA_PORT:-11435}"
echo -n "  Ollama... "
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 60 ]; then
        echo -e "${RED}timeout${NC}"
        echo "Check logs: docker logs wfhub-v2-ollama"
        exit 1
    fi
    sleep 1
done

# Wait for Aider API
AIDER_API_PORT="${AIDER_API_PORT:-8001}"
echo -n "  Aider API... "
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${AIDER_API_PORT}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}timeout${NC}"
        echo "Check logs: docker logs wfhub-v2-aider-api"
        exit 1
    fi
    sleep 1
done

# Wait for Main API
FASTAPI_PORT="${FASTAPI_PORT:-8002}"
echo -n "  Main API... "
for i in $(seq 1 30); do
    if curl -sf "http://localhost:${FASTAPI_PORT}/health/full" > /dev/null 2>&1; then
        echo -e "${GREEN}ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}timeout${NC}"
        echo "Check logs: docker logs wfhub-v2-main-api"
        exit 1
    fi
    sleep 1
done

# === Step 10: Run Database Migrations ===
echo -e "${YELLOW}[10/11] Running database migrations...${NC}"
alembic upgrade head 2>/dev/null || {
    echo "  Migrations may already be applied, checking..."
    alembic current 2>/dev/null || echo "  No pending migrations"
}
echo -e "  Migrations: ${GREEN}complete${NC}"

# === Step 11: Pull Ollama Models ===
if [ "$SKIP_MODELS" = false ]; then
    echo -e "${YELLOW}[11/11] Checking Ollama models...${NC}"
    AGENT_MODEL="${AGENT_MODEL:-qwen3:1.7b}"

    AVAILABLE_MODELS=$(curl -sf "http://localhost:${V2_OLLAMA_PORT}/api/tags" 2>/dev/null || echo '{"models":[]}')

    if echo "$AVAILABLE_MODELS" | grep -q "\"name\":\"$AGENT_MODEL\""; then
        echo -e "  Model $AGENT_MODEL: ${GREEN}available${NC}"
    else
        echo "  Pulling model $AGENT_MODEL (this may take a while)..."
        docker exec wfhub-v2-ollama ollama pull "$AGENT_MODEL"
        echo -e "  Model $AGENT_MODEL: ${GREEN}pulled${NC}"
    fi
else
    echo -e "${YELLOW}[11/11] Skipping model pull (--skip-models)${NC}"
fi

# === Success ===
echo ""
echo -e "${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "Services running:"
docker compose --env-file .env -f docker/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || docker compose --env-file .env -f docker/docker-compose.yml ps

echo ""
echo "Access the UI at:"
echo -e "  ${BLUE}https://wfhub.localhost${NC}"
echo -e "  ${BLUE}http://localhost:8002${NC} (fallback)"
echo ""
echo "Useful commands:"
echo "  ./start.sh              # Start services (after reboot)"
echo "  pytest tests/ -v        # Run tests"
echo "  source venv/bin/activate  # Activate venv for development"
echo ""

# === Open Browser ===
if [ "$NO_BROWSER" = false ]; then
    echo -e "${YELLOW}Opening browser...${NC}"

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

    open_browser "https://wfhub.localhost" || open_browser "http://localhost:8002"
fi

echo -e "${GREEN}Done!${NC}"
