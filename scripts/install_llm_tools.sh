#!/bin/bash
# ============================================================================
# LLM Tools Installation Script
# ============================================================================
# Installs and configures local LLM tools for the Agentic framework.
#
# Components installed:
#   - Ollama with GPU support (Docker)
#   - Open Interpreter (oi wrapper)
#   - Aider (ai wrapper)
#   - Kilocode (kc wrapper)
#   - LLM Launcher (llm TUI)
#   - Ollama Monitor (request/response logging)
#
# Usage:
#   ./scripts/install_llm_tools.sh              # Full install
#   ./scripts/install_llm_tools.sh --models     # Pull models only
#   ./scripts/install_llm_tools.sh --test       # Run benchmarks only
#   ./scripts/install_llm_tools.sh --help       # Show help
#
# Requirements:
#   - Docker with GPU support (nvidia-container-toolkit)
#   - Python 3.10+
#   - pip
#
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
INSTALL_DIR="${HOME}/.local/bin"
CONFIG_DIR="${HOME}/.config"
DEFAULT_MODEL="qwen2.5-coder:3b"
DEFAULT_CONTEXT=32768

# Models to pull
MODELS=(
    "qwen2.5-coder:3b"      # Fast coding model, 32k context
    "qwen2.5-coder:7b"      # Better quality, 16k context
    "qwen3:4b"              # Good reasoning, 32k context
    "deepseek-coder:1.3b"   # Fastest, 16k context
    "llava:7b"              # Vision/OCR model
)

log() { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

show_help() {
    echo "LLM Tools Installation Script"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --help      Show this help message"
    echo "  --models    Pull models only (skip tool installation)"
    echo "  --test      Run benchmarks only"
    echo "  --no-models Skip model pulling"
    echo "  --clean     Remove existing configuration"
    echo ""
    echo "Environment:"
    echo "  OLLAMA_API_BASE   Ollama API URL (default: http://localhost:11434)"
    echo "  DEFAULT_MODEL     Default model (default: qwen2.5-coder:3b)"
    echo "  DEFAULT_CONTEXT   Default context window (default: 32768)"
}

# ============================================================================
# Check Prerequisites
# ============================================================================
check_prerequisites() {
    log "Checking prerequisites..."

    # Docker
    if ! command -v docker &> /dev/null; then
        error "Docker not installed. Install Docker first."
    fi

    # Python
    if ! command -v python3 &> /dev/null; then
        error "Python 3 not installed."
    fi

    # pip packages
    for pkg in "interpreter" "aider-chat" "litellm"; do
        if ! pip show "$pkg" &> /dev/null; then
            warn "$pkg not installed. Installing..."
            pip install "$pkg" --quiet
        fi
    done

    # Check GPU
    if docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi &> /dev/null; then
        log "GPU support available"
        HAS_GPU=true
    else
        warn "No GPU support detected. Will run on CPU (slower)."
        HAS_GPU=false
    fi

    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR/open-interpreter/profiles"
}

# ============================================================================
# Start Ollama Container
# ============================================================================
start_ollama() {
    log "Starting Ollama container..."

    # Check if already running
    if docker ps --format '{{.Names}}' | grep -q '^ollama$'; then
        log "Ollama already running"
        return 0
    fi

    # Stop and remove if exists but not running
    docker stop ollama 2>/dev/null || true
    docker rm ollama 2>/dev/null || true

    # Start with GPU if available
    if $HAS_GPU; then
        docker run -d --gpus all \
            --name ollama \
            -p 11434:11434 \
            -v ollama_data:/root/.ollama \
            -e OLLAMA_DEBUG=1 \
            -e OLLAMA_FLASH_ATTENTION=1 \
            --restart unless-stopped \
            ollama/ollama:latest
    else
        docker run -d \
            --name ollama \
            -p 11434:11434 \
            -v ollama_data:/root/.ollama \
            --restart unless-stopped \
            ollama/ollama:latest
    fi

    log "Waiting for Ollama to start..."
    sleep 5

    # Wait for API
    for i in {1..30}; do
        if curl -s http://localhost:11434/api/tags > /dev/null; then
            log "Ollama ready"
            return 0
        fi
        sleep 1
    done

    error "Ollama failed to start"
}

# ============================================================================
# Pull Models
# ============================================================================
pull_models() {
    log "Pulling models..."

    for model in "${MODELS[@]}"; do
        log "Pulling $model..."
        docker exec ollama ollama pull "$model" || warn "Failed to pull $model"
    done

    log "Available models:"
    docker exec ollama ollama list
}

# ============================================================================
# Install Wrapper Scripts
# ============================================================================
install_wrappers() {
    log "Installing wrapper scripts..."

    # ========== oi - Open Interpreter ==========
    cat > "$INSTALL_DIR/oi" << 'SCRIPT'
#!/bin/bash
# Open Interpreter - Local Ollama wrapper with vision support
MODEL="${OI_MODEL:-ollama/qwen2.5-coder:3b}"
VISION_MODEL="${OI_VISION_MODEL:-ollama/llava:7b}"
API_BASE="${OI_API_BASE:-http://localhost:11434}"
CTX="${OI_CONTEXT:-32768}"
export PYTHONWARNINGS="ignore::UserWarning"

[[ "$1" == "-h" || "$1" == "--help" ]] && {
    echo "Usage: oi [options] [prompt]"
    echo "  -m MODEL     Select model"
    echo "  -c SIZE      Context window (default: 32768)"
    echo "  -v, --vision Use vision model (llava:7b)"
    echo "  --list       List models"
    echo "  --monitor    Use monitored API"
    echo ""
    echo "Examples:"
    echo "  oi                          # Interactive"
    echo "  oi \"write hello world\"      # Single task"
    echo "  oi -v \"analyze image.png\"   # Vision mode"
    exit 0
}
[[ "$1" == "--list" ]] && { docker exec ollama ollama list; exit 0; }

while [[ $# -gt 0 ]]; do
    case $1 in
        -m) MODEL="ollama/$2"; shift 2 ;;
        -c) CTX="$2"; shift 2 ;;
        -v|--vision) MODEL="$VISION_MODEL"; CTX=8192; echo "Vision mode: $MODEL"; shift ;;
        --monitor) API_BASE="http://localhost:11435"; shift ;;
        *) break ;;
    esac
done

curl -s "$API_BASE/api/tags" > /dev/null || { echo "Ollama not running"; exit 1; }
echo "Model: $MODEL | Context: $CTX"

if [ $# -eq 0 ]; then
    exec interpreter -m "$MODEL" -ab "$API_BASE" --context_window "$CTX" --no-llm_supports_functions
else
    echo "$*" | interpreter -m "$MODEL" -ab "$API_BASE" -y --context_window "$CTX" --no-llm_supports_functions
fi
SCRIPT

    # ========== ai - Aider ==========
    cat > "$INSTALL_DIR/ai" << 'SCRIPT'
#!/bin/bash
# Aider - Local Ollama wrapper
MODEL="${AI_MODEL:-ollama/qwen2.5-coder:3b}"
export OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://localhost:11434}"
exec aider --model "$MODEL" "$@"
SCRIPT

    # ========== kc - Kilocode ==========
    cat > "$INSTALL_DIR/kc" << 'SCRIPT'
#!/bin/bash
# Kilocode - Autonomous coding agent wrapper
MODEL="${KC_MODEL:-qwen2.5-coder:3b}"
CTX="${KC_CONTEXT:-32768}"
TIMEOUT="${KC_TIMEOUT:-300}"
WORKSPACE="${KC_WORKSPACE:-$(pwd)}"

[[ "$1" == "-h" || "$1" == "--help" ]] && {
    echo "Usage: kc [options] [prompt]"
    echo "  kc \"prompt\"        Run autonomously"
    echo "  kc -i              Interactive mode"
    echo "  kc -r \"prompt\"     Recursive mode"
    echo "  kc -p \"prompt\"     Plan mode"
    echo "  kc -c              Continue last session"
    exit 0
}

INTERACTIVE=false RECURSIVE=false PLAN=false CONTINUE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -m) MODEL="$2"; shift 2 ;;
        -x) CTX="$2"; shift 2 ;;
        -t) TIMEOUT="$2"; shift 2 ;;
        -w) WORKSPACE="$2"; shift 2 ;;
        -i) INTERACTIVE=true; shift ;;
        -r) RECURSIVE=true; shift ;;
        -p) PLAN=true; shift ;;
        -c) CONTINUE=true; shift ;;
        *) break ;;
    esac
done

# Update kilocode config
python3 -c "
import json, os
cfg='$HOME/.kilocode/cli/config.json'
if os.path.exists(cfg):
    with open(cfg) as f: c=json.load(f)
    c['providers'][0]['ollamaModelId']='$MODEL'
    c['providers'][0]['ollamaNumCtx']=$CTX
    with open(cfg,'w') as f: json.dump(c,f,indent=2)
" 2>/dev/null

if $INTERACTIVE; then
    exec kilocode -w "$WORKSPACE" -mo "$MODEL"
elif $CONTINUE; then
    exec kilocode --continue -w "$WORKSPACE" -mo "$MODEL"
elif $RECURSIVE; then
    kilocode --auto --yolo -m code -w "$WORKSPACE" -t "$TIMEOUT" -mo "$MODEL" "$*"
elif $PLAN; then
    kilocode --auto --yolo -m architect -w "$WORKSPACE" -t "$TIMEOUT" -mo "$MODEL" "$*"
elif [ -n "$*" ]; then
    kilocode --auto --yolo -m code -w "$WORKSPACE" -t "$TIMEOUT" -mo "$MODEL" "$*"
else
    exec kilocode -w "$WORKSPACE" -mo "$MODEL"
fi
SCRIPT

    # ========== llm - TUI Launcher ==========
    cat > "$INSTALL_DIR/llm" << 'SCRIPT'
#!/usr/bin/env python3
"""LLM Tool Launcher - TUI for selecting models and tools."""
import subprocess, sys, os, json, urllib.request

API = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
CTX = {"qwen2.5-coder:3b": 32768, "qwen3:4b": 32768, "qwen2.5-coder:7b": 16384,
       "deepseek-coder:1.3b": 16384, "llava:7b": 4096}
TOOLS = {"oi": "Open Interpreter", "aider": "Aider", "kc": "Kilocode", "chat": "Ollama Chat"}

def get_models():
    try:
        with urllib.request.urlopen(f"{API}/api/tags", timeout=5) as r:
            return json.loads(r.read()).get("models", [])
    except: return []

def menu(title, opts):
    print(f"\n\033[1m{title}\033[0m\n" + "-"*40)
    for i, o in enumerate(opts, 1): print(f"  {i}) {o}")
    print("  q) Quit\n")
    while True:
        try:
            c = input("Select: ").strip().lower()
            if c == 'q': return None
            if 0 <= int(c)-1 < len(opts): return opts[int(c)-1]
        except: pass

def main():
    args = sys.argv[1:]
    if args and args[0] == "models":
        for m in get_models():
            print(f"{m['name']:30} {m['size']/(1024**3):5.1f}GB ctx:{CTX.get(m['name'],16384)//1024}k")
        return
    if args and args[0] == "bench":
        for model in ["qwen2.5-coder:3b", "qwen3:4b"]:
            try:
                d = json.dumps({"model": model, "prompt": "def f():", "stream": False,
                               "options": {"num_ctx": 32768}}).encode()
                with urllib.request.urlopen(urllib.request.Request(f"{API}/api/generate", d), timeout=60) as r:
                    print(f"  {model}: {json.loads(r.read())['total_duration']/1e9:.1f}s")
            except Exception as e: print(f"  {model}: FAIL ({e})")
        return

    print("\033[1m\n╔══════════════════════════════════════╗\n║        LLM Tool Launcher             ║\n╚══════════════════════════════════════╝\033[0m")
    tool = menu("Select Tool", list(TOOLS.keys()))
    if not tool: return
    models = [m["name"] for m in get_models()]
    model = menu("Select Model", models) if models else None
    if not model: return

    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore::UserWarning"
    if tool == "oi": subprocess.run(["oi", "-m", model], env=env)
    elif tool == "aider": subprocess.run(["aider", "--model", f"ollama/{model}"], env=env)
    elif tool == "kc": subprocess.run(["kc", "-m", model, "-i"], env=env)
    elif tool == "chat": subprocess.run(["docker", "exec", "-it", "ollama", "ollama", "run", model])

if __name__ == "__main__": main()
SCRIPT

    # ========== ollama-monitor - Request Logger ==========
    cat > "$INSTALL_DIR/ollama-monitor" << 'SCRIPT'
#!/usr/bin/env python3
"""Ollama Request/Response Monitor - Proxy that logs all API calls."""
import http.server, urllib.request, json, sys, time
from datetime import datetime

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
API = "http://localhost:11434"
C = {"cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
     "magenta": "\033[35m", "red": "\033[31m", "reset": "\033[0m", "bold": "\033[1m"}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _proxy(self, method):
        t0 = time.time()
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        print(f"\n{C['cyan']}{'─'*60}\n[{datetime.now():%H:%M:%S}] {method} {self.path}{C['reset']}")
        if body:
            try:
                j = json.loads(body)
                print(f"{C['yellow']}Model: {j.get('model')} | Prompt: {str(j.get('prompt',''))[:100]}...{C['reset']}")
            except: pass
        try:
            req = urllib.request.Request(f"{API}{self.path}", body or None, method=method,
                headers={k: v for k, v in self.headers.items() if k.lower() != 'host'})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
                self.send_response(r.status)
                for h, v in r.getheaders():
                    if h.lower() not in ('transfer-encoding', 'connection'): self.send_header(h, v)
                self.end_headers()
                self.wfile.write(data)
                try:
                    j = json.loads(data)
                    print(f"{C['green']}Response: {r.status} ({time.time()-t0:.1f}s){C['reset']}")
                    if 'response' in j: print(f"{C['magenta']}Output: {j['response'][:200]}...{C['reset']}")
                    if 'total_duration' in j: print(f"Tokens: {j.get('prompt_eval_count',0)}+{j.get('eval_count',0)} in {j['total_duration']/1e9:.1f}s")
                except: pass
        except Exception as e:
            print(f"{C['red']}Error: {e}{C['reset']}")
            self.send_response(500); self.end_headers()
    def do_GET(self): self._proxy("GET")
    def do_POST(self): self._proxy("POST")

print(f"{C['bold']}Ollama Monitor - Port {PORT} → {API}{C['reset']}\nUse: OI_API_BASE=http://localhost:{PORT} oi")
try: http.server.HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
except KeyboardInterrupt: print("\nStopped")
SCRIPT

    # Make all executable
    chmod +x "$INSTALL_DIR"/{oi,ai,kc,llm,ollama-monitor}
    log "Wrapper scripts installed to $INSTALL_DIR"
}

# ============================================================================
# Configure Tools
# ============================================================================
configure_tools() {
    log "Configuring tools..."

    # Open Interpreter default profile
    cat > "$CONFIG_DIR/open-interpreter/profiles/default.yaml" << EOF
llm:
  model: "ollama/$DEFAULT_MODEL"
  api_base: "http://localhost:11434"
  temperature: 0
  context_window: $DEFAULT_CONTEXT
  max_tokens: 2000
  supports_functions: false

computer:
  import_computer_api: False

custom_instructions: "Be concise. Write working code. Execute it."

auto_run: False
safe_mode: "off"
offline: True

version: 0.2.5
EOF

    # Aider config
    cat > "$HOME/.aider.conf.yml" << EOF
model: ollama/$DEFAULT_MODEL
auto-commits: false
stream: true
pretty: true
dark-mode: true
EOF

    # Kilocode cache fix
    mkdir -p "$HOME/.kilocode/cli/global/cache"
    cat > "$HOME/.kilocode/cli/global/cache/ollama_models.json" << EOF
{
  "qwen2.5-coder:3b": {"maxTokens": 32768, "contextWindow": 32768, "supportsImages": false},
  "qwen2.5-coder:7b": {"maxTokens": 32768, "contextWindow": 32768, "supportsImages": false},
  "qwen3:4b": {"maxTokens": 65536, "contextWindow": 65536, "supportsImages": false},
  "deepseek-coder:1.3b": {"maxTokens": 16384, "contextWindow": 16384, "supportsImages": false},
  "llava:7b": {"maxTokens": 4096, "contextWindow": 4096, "supportsImages": true}
}
EOF

    log "Tool configurations created"
}

# ============================================================================
# Add to PATH
# ============================================================================
setup_path() {
    log "Setting up PATH..."

    if ! grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        log "Added ~/.local/bin to PATH in ~/.bashrc"
    fi

    export PATH="$HOME/.local/bin:$PATH"
}

# ============================================================================
# Run Benchmarks
# ============================================================================
run_benchmarks() {
    log "Running benchmarks..."

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    LLM Benchmark Results                     ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║ Model                    │ Context │    Time │ Status       ║"
    echo "╠══════════════════════════════════════════════════════════════╣"

    for model in "qwen2.5-coder:3b" "qwen3:4b" "deepseek-coder:1.3b"; do
        for ctx in 16384 32768; do
            result=$(curl -s http://localhost:11434/api/generate -d "{
                \"model\": \"$model\",
                \"prompt\": \"def quicksort(arr):\",
                \"stream\": false,
                \"options\": {\"num_ctx\": $ctx}
            }" --max-time 90 2>&1)

            time=$(echo "$result" | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'{r.get(\"total_duration\",0)/1e9:.1f}')" 2>/dev/null || echo "FAIL")

            if [[ "$time" == "FAIL" ]]; then
                status="✗ Error"
            elif (( $(echo "$time < 15" | bc -l) )); then
                status="✓ Fast"
            elif (( $(echo "$time < 30" | bc -l) )); then
                status="✓ Good"
            else
                status="⚠ Slow"
            fi

            printf "║ %-24s │ %6dk │ %6ss │ %-12s ║\n" "$model" "$((ctx/1024))" "$time" "$status"
        done
    done

    echo "╚══════════════════════════════════════════════════════════════╝"
}

# ============================================================================
# Main
# ============================================================================
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           LLM Tools Installation Script                      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    SKIP_MODELS=false
    MODELS_ONLY=false
    TEST_ONLY=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --help) show_help; exit 0 ;;
            --models) MODELS_ONLY=true; shift ;;
            --test) TEST_ONLY=true; shift ;;
            --no-models) SKIP_MODELS=true; shift ;;
            --clean) rm -rf "$CONFIG_DIR/open-interpreter" "$HOME/.aider.conf.yml"; shift ;;
            *) shift ;;
        esac
    done

    if $TEST_ONLY; then
        run_benchmarks
        exit 0
    fi

    check_prerequisites
    start_ollama

    if $MODELS_ONLY; then
        pull_models
        exit 0
    fi

    install_wrappers
    configure_tools
    setup_path

    if ! $SKIP_MODELS; then
        pull_models
    fi

    run_benchmarks

    echo ""
    log "Installation complete!"
    echo ""
    echo "Commands available (restart shell or run: source ~/.bashrc):"
    echo "  llm              - TUI launcher for all tools"
    echo "  llm models       - List available models"
    echo "  llm bench        - Run benchmarks"
    echo "  oi               - Open Interpreter"
    echo "  oi \"prompt\"      - One-shot execution"
    echo "  ai               - Aider pair programmer"
    echo "  kc               - Kilocode autonomous agent"
    echo "  kc -r \"task\"     - Recursive mode"
    echo "  ollama-monitor   - Request/response logging"
    echo ""
}

main "$@"
