# LLM Notes (Local Models)

This document captures local LLM choices, size tradeoffs, and agent behavior
observations for Workflow Hub. Update as models/tooling change.

## Candidate Models (Lean to Mid)

Qwen3-8B-Coder
- Size: ~5GB (Q4) / ~9GB (Q8)
- Strength: all-around coding
- Notes: large context (131k), strong Python/JS performance

DeepSeek-R1-Distill-Qwen-7B
- Size: ~5GB (Q4) / ~8GB (Q8)
- Strength: complex logic / debugging
- Notes: chain-of-thought reasoning before answers

Llama-4-8B-Instruct
- Size: ~5GB (Q4) / ~9GB (Q8)
- Strength: general help & shell
- Notes: reliable at following instructions / terminal commands

Mistral-Nemo-12B (v2)
- Size: ~8GB (Q4) / ~13GB (Q8)
- Strength: long context
- Notes: balanced size vs intelligence for large prompts

## Agent Tooling Notes

- Small/lean models often emit tool calls as JSON text instead of native tool calls.
- For reliability, enable:
  - AGENT_CLI_TOOL_CHOICE=any (force tool usage)
  - AGENT_CLI_TOOL_FALLBACK=1 (parse JSON tool calls in text)
- If HTTPS trust is not installed, use:
  - AGENT_CLI_OLLAMA_BASE=http://localhost:11435
  - AGENT_CLI_SSL_VERIFY=0

## Known Issues

- qwen3:1.7b pull timed out on this host (retry needed).
- qwen3:4b not pulled yet in Ollama.
- qwen2.5-coder:3b outputs tool calls as JSON text; fallback parser required.
