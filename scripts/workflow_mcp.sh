#!/bin/bash
# Wrapper script to run workflow_mcp with proper environment
# Used by Claude Code and Goose MCP integrations

cd /Users/mz/Dropbox/_CODING/Agentic
source venv/bin/activate
source .env

exec python manage.py workflow_mcp "$@"
