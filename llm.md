# LLM Model Reference (Canonical)

> Single source of truth for local model choices. Referenced by AGENTS.md and README.md.

## Hardware Constraints

**GPU**: 4GB VRAM (GTX 1650 or similar)

## Active Models

| Model | Size | Use Case | Tool Calling | Fits 4GB? | Status |
|-------|------|----------|--------------|-----------|--------|
| **hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M** | ~3.0GB | Default - coding + vision (GGUF Q4) | Native | Yes | **Current default** |
| gemma3:4b | 3.3GB | Fast, reliable fallback | Native | Yes | Available |
| qwen3:1.7b | 1.4GB | Small coding tasks | Native | Yes | Available |
| qwen3:0.6b | 0.5GB | Fastest, lightweight | Native | Yes | Available |
| qwen2.5-coder:3b | 1.9GB | Coding optimized | Text fallback | Yes | Available |

## Candidate Models (Not Yet Deployed)

| Model | Size (Q4) | Strength | Notes |
|-------|-----------|----------|-------|
| Qwen3-8B-Coder | ~5GB | All-around coding | 131k context, strong Python/JS. Won't fit 4GB VRAM. |
| DeepSeek-R1-Distill-Qwen-7B | ~5GB | Complex logic/debugging | Chain-of-thought reasoning. Won't fit 4GB VRAM. |
| Llama-4-8B-Instruct | ~5GB | General help & shell | Reliable instruction following. Won't fit 4GB VRAM. |
| Mistral-Nemo-12B | ~8GB | Long context | Balanced for large prompts. Won't fit 4GB VRAM. |

## Vision Models

| Model | Size | Speed | Notes |
|-------|------|-------|-------|
| **hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M** | ~3.0GB | Fast | Primary vision model (GGUF Q4) |
| gemma3:4b | 3.3GB | Fast (~5s) | Fallback vision model |
| qwen3-vl:8b | ~5GB | Medium (~30s) | Fallback. Won't fit 4GB VRAM. |

## Agent Tooling Notes

- Small/lean models often emit tool calls as JSON text instead of native tool calls.
- For reliability with smaller models, enable:
  - `AGENT_CLI_TOOL_CHOICE=any` (force tool usage)
  - `AGENT_CLI_TOOL_FALLBACK=1` (parse JSON tool calls in text)
- If HTTPS trust is not installed for local Ollama:
  - `AGENT_CLI_OLLAMA_BASE=http://localhost:11435`
  - `AGENT_CLI_SSL_VERIFY=0`

## Ollama Optimizations

Set in `docker/docker-compose.yml`:
- `OLLAMA_KV_CACHE_TYPE=q8_0` - Halves KV cache memory
- `OLLAMA_FLASH_ATTENTION=1` - Reduces VRAM, increases speed
- `OLLAMA_MAX_LOADED_MODELS=1` - Single model in memory

## Pull Commands

```bash
ollama pull hf.co/Qwen/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M  # Primary (required)
ollama pull gemma3:4b           # Fallback
ollama pull qwen3:1.7b          # Small coding
ollama pull nomic-embed-text    # Embeddings (for agentmem)
```
