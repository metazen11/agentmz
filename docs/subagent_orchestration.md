# Subagent Orchestration Guide

> How to use Codex and Gemini as subagents from Claude Code

## Available Subagents

| Agent | Command | Model | Best For |
|-------|---------|-------|----------|
| Codex | `codex exec` | gpt-5.1-codex-mini | Code generation, file creation, refactoring |
| Gemini | `gemini -p` | gemini-2.5-pro | Research, analysis, documentation |

## Codex CLI

**Non-interactive execution:**
```bash
codex exec --full-auto -C /path/to/project "prompt here"
```

**Key flags:**
- `--full-auto` - Sandboxed auto-execution (workspace-write)
- `-C /path` - Working directory
- `-o file.txt` - Capture final response to file
- `--json` - Output as JSONL events
- `-m model` - Override model

**Example - Code generation:**
```bash
codex exec --full-auto -C . -o /tmp/output.txt "Create a Python function that validates email addresses using regex"
```

**Example - File exploration:**
```bash
codex exec --full-auto "List files in src/ and describe what each does"
```

## Gemini CLI

**Non-interactive execution:**
```bash
gemini -p "prompt here" --yolo
```

**Key flags:**
- `-p "prompt"` - Non-interactive prompt
- `--yolo` - Auto-approve all actions
- `-o json` - JSON output format
- `-m model` - Override model
- `--sandbox` - Run in sandbox mode

**Example - Research:**
```bash
gemini -p "Analyze the architecture in ARCHITECTURE.md and suggest improvements" --yolo
```

**Example - Documentation:**
```bash
gemini -p "Generate API documentation for the endpoints in main.py" --yolo -o json
```

## Orchestration Patterns

### 1. Specific Task Delegation

Be explicit about:
- File paths (absolute or relative to working dir)
- Class/function names
- Expected output format
- Constraints (file size, style, etc.)

**Good prompt:**
```
Create forge/hooks/auto_commit.py with a post_tool function that:
- Takes tool_name, args, result parameters
- If tool_name is 'write_file', runs git add and git commit
- Returns None
- Keep under 50 lines
```

**Bad prompt:**
```
Add auto-commit hook
```

### 2. Parallel Execution

Run both agents in background for independent tasks:
```bash
codex exec --full-auto "Task 1" &
gemini -p "Task 2" --yolo &
wait
```

### 3. Sequential Pipeline

Codex generates, Gemini reviews:
```bash
codex exec --full-auto -o /tmp/code.py "Write the function"
gemini -p "Review /tmp/code.py for security issues" --yolo
```

### 4. Capture and Inspect

Always capture output for review:
```bash
codex exec --full-auto -o /tmp/codex_output.txt "Create X"
cat /tmp/codex_output.txt  # Review before proceeding
```

## Best Practices

1. **Read AGENTS.md** - Include instruction to read project conventions
2. **Specify paths** - Use absolute paths or clear relative paths
3. **Set constraints** - Line limits, style requirements, naming conventions
4. **Capture output** - Always use `-o` flag for important results
5. **Review results** - Inspect generated code before committing
6. **One task per call** - Keep prompts focused on single objectives

## Strengths by Agent

### Codex
- Fast code generation
- File system operations
- Shell command execution
- Understands project context via AGENTS.md/CLAUDE.md

### Gemini
- Deep analysis and reasoning
- Documentation generation
- Code review and security analysis
- Research and comparison tasks

## Integration with Forge

The `forge/subagent.py` module wraps Claude Code for embedding Forge as a tool:
- Session persistence
- One-shot delegation
- CLI isolation

Future: Two-agent coordination (Claude + local Forge)
