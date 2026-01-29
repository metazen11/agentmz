#!/usr/bin/env bash
set -euo pipefail

export AGENT_CLI_DEBUG=1
export AGENT_CLI_DEBUG_PAYLOAD=1
export AGENT_CLI_SSL_VERIFY=0
export AGENT_CLI_TOOL_CHOICE=any
export AGENT_CLI_TOOL_FALLBACK=1

./.venv312/Scripts/python.exe scripts/agent_cli.py --prompt "First call read_file on index.html, then apply_patch to replace the invalid <class=animated/> with <h1 class=animated>Hello World</h1>. Do not use write_file or delete_file." --model qwen2.5-coder:3b --project-name poc-fallback-sh --max-iters 4
