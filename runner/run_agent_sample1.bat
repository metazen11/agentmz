@echo off
setlocal
set AGENT_CLI_DEBUG=1
set AGENT_CLI_DEBUG_PAYLOAD=1
set AGENT_CLI_SSL_VERIFY=0
set AGENT_CLI_TOOL_CHOICE=any
set AGENT_CLI_TOOL_FALLBACK=1

.\.venv312\Scripts\python.exe scripts\agent_cli.py --prompt "First call read_file on index.html, then apply_patch to replace the invalid <class=animated/> with <h1 class=animated>Hello World</h1>. Do not use write_file or delete_file." --model qwen2.5-coder:3b --project-name poc-fallback-bat --max-iters 4
endlocal
