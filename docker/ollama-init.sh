#!/bin/bash
# Ollama initialization script
# Runs on container startup to ensure optimized models are created

set -e

echo "=== Ollama Init Script ==="

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
until ollama list > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama is ready"

# Check if base model exists, pull if not
if ! ollama list | grep -q "qwen2.5-coder:14b"; then
    echo "Pulling qwen2.5-coder:14b base model..."
    ollama pull qwen2.5-coder:14b
fi

# Check if optimized model exists, create if not
if ! ollama list | grep -q "qwen-coder-optimized"; then
    echo "Creating optimized model..."

    # Create Modelfile
    cat > /tmp/Modelfile << 'EOF'
# Optimized qwen2.5-coder for T500 (4GB VRAM) + 32GB RAM
# Greedy GPU allocation with RAM spillover

FROM qwen2.5-coder:14b

# Force the engine to fill your 4GB VRAM first
# 99 is a 'greedy' value; Ollama will take all 4GB and spill the rest to RAM
PARAMETER num_gpu 99

# Give Aider a large 12k context window (uses ~2.5GB of your 32GB RAM)
PARAMETER num_ctx 12288

# Stop the model from hallucinating tool calls
PARAMETER temperature 0
EOF

    # Create the optimized model
    ollama create qwen-coder-optimized -f /tmp/Modelfile
    echo "Optimized model created successfully"
else
    echo "Optimized model already exists"
fi

# Preload the model to warm it up
echo "Preloading model..."
curl -s http://localhost:11434/api/generate -d '{"model": "qwen-coder-optimized", "prompt": "hi", "stream": false}' > /dev/null 2>&1 || true

echo "=== Ollama Init Complete ==="
ollama list
ollama ps
