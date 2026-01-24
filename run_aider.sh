#!/bin/bash
# Run aider interactively in the aider-api container
# Usage: ./run_aider.sh [-s1|-s2|-s3] [workspace] [files...]
# Model sizes: -s1 = 0.7b (default), -s2 = 1.7b, -s3 = 3b
# Example: ./run_aider.sh poc chat.html        # uses qwen3:0.6b
#          ./run_aider.sh -s2 poc chat.html    # uses qwen3:1.7b
#          ./run_aider.sh -s3                  # uses qwen2.5-coder:3b

set -e  # Exit on error

# Load .env for git identity
if [ -f .env ]; then
    export $(grep -E '^(GIT_USER_NAME|GIT_USER_EMAIL)=' .env | xargs 2>/dev/null) 2>/dev/null || true
fi

# Default to smallest model
MODEL="qwen3:0.6b"

# Parse model size flag
case "${1:-}" in
    -s1) MODEL="qwen3:0.6b";        shift ;;
    -s2) MODEL="qwen3:1.7b";        shift ;;
    -s3) MODEL="qwen2.5-coder:3b";  shift ;;
esac

WORKSPACE="${1:-}"
if [ -n "$1" ]; then shift; fi
FILES="$@"

# Default git identity if not set
GIT_USER_NAME="${GIT_USER_NAME:-Aider Agent}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-aider@local}"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q '^wfhub-v2-aider-api$'; then
    echo "Error: Container wfhub-v2-aider-api is not running"
    echo "Start it with: cd docker && docker-compose up -d"
    exit 1
fi

# Determine working directory
# If workspace specified, use /v2/workspaces/$WORKSPACE
# Otherwise use /v2 (project root)
if [ -n "$WORKSPACE" ]; then
  WORKDIR="/workspaces/$WORKSPACE"
else
  WORKDIR="/"
fi

echo "Using model: $MODEL"
echo "Working dir: $WORKDIR"
echo "Git user: $GIT_USER_NAME <$GIT_USER_EMAIL>"

# Set git config in container before running aider
docker exec \
  -w "$WORKDIR" \
  wfhub-v2-aider-api \
  git config user.name "$GIT_USER_NAME" 2>/dev/null || true

docker exec \
  -w "$WORKDIR" \
  wfhub-v2-aider-api \
  git config user.email "$GIT_USER_EMAIL" 2>/dev/null || true

# Route through main-api proxy for HTTP logging
docker exec -it \
  -e OLLAMA_API_BASE=http://wfhub-v2-main-api:8002/ollama \
  -e GIT_AUTHOR_NAME="$GIT_USER_NAME" \
  -e GIT_AUTHOR_EMAIL="$GIT_USER_EMAIL" \
  -e GIT_COMMITTER_NAME="$GIT_USER_NAME" \
  -e GIT_COMMITTER_EMAIL="$GIT_USER_EMAIL" \
  -w "$WORKDIR" \
  wfhub-v2-aider-api \
  aider --model "ollama_chat/$MODEL" --yes --auto-commits $FILES
