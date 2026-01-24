#!/usr/bin/env bash
set -euo pipefail

# Use AGENTMZ_DIR if set, otherwise derive from script location
if [ -n "${AGENTMZ_DIR:-}" ]; then
  SCRIPT_DIR="$AGENTMZ_DIR"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Load .env if present
if [ -f "${SCRIPT_DIR}/.env" ]; then
  set -a
  source "${SCRIPT_DIR}/.env"
  set +a
fi

# Defaults
MODEL="${AIDER_MODEL:-ollama_chat/qwen3:0.6b}"
OLLAMA_BASE="${OLLAMA_API_BASE_LOCAL:-${OLLAMA_API_BASE:-http://localhost:8002/ollama}}"
WORKSPACE=""
PROMPT=""
PROMPT_FILE=""
IMAGE=""
FILES=()
HEADLESS=false
VERBOSE=false
VERIFY=false
ITERATIONS=1

show_help() {
  cat <<'EOF'
agent - AI Coding Assistant

Usage:
  agent [options] [files...]

Options:
  -p, --prompt "text"     Inline prompt
  -pf, --prompt-file FILE Read prompt from file
  -w, --workspace DIR     Working directory
  -i, --image FILE        Include image (for vision models)
  -m, --model MODEL       Model name (e.g., qwen3:0.6b)
  -s1                     Use smallest model (qwen3:0.6b)
  -s2                     Use small model (qwen3:1.7b)
  -s3                     Use medium model (qwen2.5-coder:3b)
  -s4                     Use large model (qwen2.5-coder:7b)
  --yolo                  Run without interaction (auto-yes)
  --verify                Chain: run prompt, then verify & fix issues
  --iterations N          Number of verify iterations (default: 1)
  -v, --verbose           Show debug info
  -h, --help              Show this help

Examples:
  agent                                    # Interactive session
  agent -p "Fix the bug" main.py           # Quick fix
  agent -pf task.txt -w ./myproject        # Prompt from file
  agent -i screenshot.png -p "Implement this UI"  # With image
  agent --yolo -p "Add tests" src/         # YOLO mode (auto-yes)
  agent --yolo --verify -p "Add feature"   # Run + 1 verify pass
  agent --yolo --verify --iterations 3 -p "Refactor" db.py  # 3 verify passes

Chained Iterations (--verify):
  Step 1: Run your main prompt
  Step 2+: Verify & fix (checks bugs, errors, intent mismatch)
  Each verify pass reviews changes and fixes issues found

Environment:
  AGENTMZ_DIR       Project root directory
  AIDER_MODEL       Default model (ollama_chat/...)
  OLLAMA_API_BASE   Ollama endpoint URL
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -p|--prompt)
      PROMPT="$2"
      shift 2
      ;;
    -pf|--prompt-file)
      PROMPT_FILE="$2"
      shift 2
      ;;
    -w|--workspace)
      WORKSPACE="$2"
      shift 2
      ;;
    -i|--image)
      IMAGE="$2"
      shift 2
      ;;
    -m|--model)
      MODEL="ollama_chat/$2"
      shift 2
      ;;
    -s1)
      MODEL="ollama_chat/qwen3:0.6b"
      shift
      ;;
    -s2)
      MODEL="ollama_chat/qwen3:1.7b"
      shift
      ;;
    -s3)
      MODEL="ollama_chat/qwen2.5-coder:3b"
      shift
      ;;
    -s4)
      MODEL="ollama_chat/qwen2.5-coder:7b"
      shift
      ;;
    --yolo)
      HEADLESS=true
      shift
      ;;
    --verify)
      VERIFY=true
      HEADLESS=true  # verify implies yolo
      shift
      ;;
    --iterations)
      ITERATIONS="$2"
      shift 2
      ;;
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    --)
      shift
      FILES+=("$@")
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      echo "Use --help for usage" >&2
      exit 1
      ;;
    *)
      FILES+=("$1")
      shift
      ;;
  esac
done

# Validate prompt options (mutually exclusive)
if [ -n "$PROMPT" ] && [ -n "$PROMPT_FILE" ]; then
  echo "Error: Use either -p or -pf, not both" >&2
  exit 1
fi

# Read prompt from file if specified
if [ -n "$PROMPT_FILE" ]; then
  if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: Prompt file not found: $PROMPT_FILE" >&2
    exit 1
  fi
  PROMPT="$(cat "$PROMPT_FILE")"
fi

# Set workspace (default to cwd if not specified)
if [ -n "$WORKSPACE" ]; then
  if [ ! -d "$WORKSPACE" ]; then
    echo "Error: Workspace not found: $WORKSPACE" >&2
    exit 1
  fi
  cd "$WORKSPACE"
fi
# Now in the target workspace (either specified or cwd)
WORKSPACE_DIR="$(pwd)"

# Build aider command
AIDER_ARGS=(
  --model "$MODEL"
  --auto-commits
)

# Headless mode
if [ "$HEADLESS" = true ] || [ -n "$PROMPT" ]; then
  AIDER_ARGS+=(--yes)
fi

# Process image through vision API if provided
IMAGE_DESCRIPTION=""
if [ -n "$IMAGE" ]; then
  if [ ! -f "$IMAGE" ]; then
    echo "Error: Image not found: $IMAGE" >&2
    exit 1
  fi

  echo "Processing image through vision API..." >&2

  # Base64 encode the image
  IMAGE_BASE64=$(base64 -w0 "$IMAGE" 2>/dev/null || base64 "$IMAGE")
  IMAGE_FILENAME=$(basename "$IMAGE")

  # Call vision API
  VISION_RESPONSE=$(curl -sf "http://localhost:8002/api/vision/describe" \
    -H "Content-Type: application/json" \
    -d "{\"image\": \"$IMAGE_BASE64\", \"filename\": \"$IMAGE_FILENAME\", \"context\": \"Describe this image in detail for a developer who needs to implement it.\"}" \
    2>/dev/null)

  if [ $? -eq 0 ] && [ -n "$VISION_RESPONSE" ]; then
    # Extract description from response
    IMAGE_DESCRIPTION=$(echo "$VISION_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null || echo "")
    if [ -n "$IMAGE_DESCRIPTION" ]; then
      echo "Image analyzed successfully" >&2
    else
      echo "Warning: Could not extract image description" >&2
    fi
  else
    echo "Warning: Vision API unavailable, image will be skipped" >&2
  fi
fi

# Add prompt (with image description if available)
if [ -n "$IMAGE_DESCRIPTION" ] && [ -n "$PROMPT" ]; then
  FULL_PROMPT="IMAGE DESCRIPTION:
$IMAGE_DESCRIPTION

USER REQUEST:
$PROMPT"
  AIDER_ARGS+=(--message "$FULL_PROMPT")
elif [ -n "$IMAGE_DESCRIPTION" ]; then
  AIDER_ARGS+=(--message "IMAGE DESCRIPTION:
$IMAGE_DESCRIPTION

Please implement or analyze based on this image.")
elif [ -n "$PROMPT" ]; then
  AIDER_ARGS+=(--message "$PROMPT")
fi

# Add files
if [ ${#FILES[@]} -gt 0 ]; then
  AIDER_ARGS+=("${FILES[@]}")
fi

# Export Ollama endpoint
export OLLAMA_API_BASE="$OLLAMA_BASE"
export OLLAMA_URL="$OLLAMA_BASE"

# Debug output
if [ "$VERBOSE" = true ]; then
  echo "=== Agent Debug ===" >&2
  echo "Model: $MODEL" >&2
  echo "Ollama: $OLLAMA_BASE" >&2
  echo "Workspace: $WORKSPACE_DIR" >&2
  echo "Prompt: ${PROMPT:-(interactive)}" >&2
  echo "Image: ${IMAGE:-(none)}" >&2
  echo "Image analyzed: ${IMAGE_DESCRIPTION:+(yes)}" >&2
  echo "Files: ${FILES[*]:-(none)}" >&2
  echo "Verify: $VERIFY (iterations: $ITERATIONS)" >&2
  echo "Command: aider ${AIDER_ARGS[*]}" >&2
  echo "===================" >&2
else
  echo "Workspace: $WORKSPACE_DIR" >&2
fi

# Run aider
if [ "$VERIFY" = false ]; then
  # Simple run
  exec aider "${AIDER_ARGS[@]}"
else
  # Chain: run prompt, then verify iterations
  echo "=== Step 1: Running main prompt ===" >&2
  aider "${AIDER_ARGS[@]}"

  # Build verify args (same files, different prompt)
  VERIFY_ARGS=(
    --model "$MODEL"
    --auto-commits
    --yes
  )

  if [ ${#FILES[@]} -gt 0 ]; then
    VERIFY_ARGS+=("${FILES[@]}")
  fi

  for ((i=1; i<=ITERATIONS; i++)); do
    echo "" >&2
    echo "=== Step $((i+1)): Verify & fix (iteration $i/$ITERATIONS) ===" >&2

    VERIFY_PROMPT="Review the recent changes. Check for:
1. Bugs or logic errors
2. Missing error handling
3. Code that doesn't match the original intent
4. Syntax errors or typos

If you find issues, fix them. If everything looks good, say 'LGTM - no issues found'."

    aider "${VERIFY_ARGS[@]}" --message "$VERIFY_PROMPT"
  done

  echo "" >&2
  echo "=== Done: $((ITERATIONS+1)) total passes ===" >&2
fi
