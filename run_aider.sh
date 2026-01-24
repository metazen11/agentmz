#!/bin/bash
# Run aider interactively in the aider-api container
# Usage: ./run_aider.sh [workspace] [files...]
# Example: ./run_aider.sh poc chat.html
#          ./run_aider.sh   # defaults to current dir mapped to /v2

WORKSPACE="${1:-}"
shift
FILES="$@"

# If running from v2 directory, map to /v2 in container
docker exec -it \
  -e OLLAMA_API_BASE=http://wfhub-v2-ollama:11434 \
  -w /v2${WORKSPACE:+/workspaces/$WORKSPACE} \
  wfhub-v2-aider-api \
  aider --model ollama_chat/qwen2.5-coder:3b --yes --auto-commits $FILES
