#!/bin/bash
# Restart ollama service inside the container
#
# This script is executed via SSH from main-api to restart the
# ollama process without restarting the entire container.
#
# Note: If ollama is PID 1, we can't kill it without stopping the container.
# In that case, we just verify ollama is healthy or trigger model reload.
#
# Exit codes:
#   0: Success - ollama is responding
#   1: Failure - ollama is not responding

OLLAMA_PORT="${OLLAMA_PORT:-11434}"
MAX_WAIT="${OLLAMA_RESTART_TIMEOUT:-30}"

# Check if ollama is PID 1 (container's main process)
OLLAMA_PID=$(pgrep -f "ollama serve" | head -1)

if [ "$OLLAMA_PID" = "1" ]; then
    echo "[RESTART] Ollama is PID 1 - cannot kill without stopping container"
    echo "[RESTART] Checking if ollama is healthy..."

    if curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
        echo "[RESTART] Ollama is healthy and responding"
        exit 0
    else
        echo "[RESTART] Ollama is not responding - container restart required"
        exit 1
    fi
fi

# Ollama is not PID 1, we can restart it
echo "[RESTART] Stopping ollama (PID $OLLAMA_PID)..."
kill $OLLAMA_PID || true

# Wait for process to stop
sleep 2

echo "[RESTART] Starting ollama..."
nohup ollama serve > /var/log/ollama.log 2>&1 &
NEW_PID=$!

echo "[RESTART] Ollama started with PID $NEW_PID"
echo "[RESTART] Waiting for ollama to be ready (max ${MAX_WAIT}s)..."

for i in $(seq 1 $MAX_WAIT); do
    if curl -s "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
        echo "[RESTART] Ollama restarted successfully after ${i}s"
        exit 0
    fi
    sleep 1
done

echo "[RESTART] Timeout waiting for ollama after ${MAX_WAIT}s"
exit 1
