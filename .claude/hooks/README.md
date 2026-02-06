# Claude Code Hooks

Cross-platform code quality hooks for Claude Code (Mac, Linux, Windows).

## Quick Install

```bash
# Mac/Linux
python3 .claude/hooks/install.py

# Windows
python .claude\hooks\install.py
```

## What Gets Installed

1. **Claude Code Settings** (`.claude/settings.local.json`)
   - PostToolUse hook runs after every Write/Edit
   - Validates code quality automatically

2. **Git Pre-Commit Hook** (`.git/hooks/pre-commit`)
   - Same checks run before every commit
   - Blocks commits with security issues

## Code Review Checks

### 1. Simplicity
- Deep class inheritance chains
- Overly complex one-liners
- Nested callbacks (JS)

### 2. Security (OWASP)
- SQL injection patterns
- Command injection risks
- Hardcoded secrets/passwords
- XSS vulnerabilities (innerHTML)
- eval() usage
- Pickle deserialization

### 3. Naming Conventions
- **Python**: snake_case functions, PascalCase classes
- **JavaScript**: camelCase functions, PascalCase classes
- Descriptive variable names

### 4. Syntax Validation
- Python: `py_compile`
- JavaScript: `node --check`
- JSON: valid structure
- Bash: `bash -n`

### 5. Documentation
- Docstring coverage (Python)
- JSDoc comments (JavaScript)
- Line length warnings (>120 chars)

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 2 | Blocking error - Claude must fix issues |

## Bypass Options

**Claude Code** (not recommended):
```bash
# Temporarily disable by renaming settings
mv .claude/settings.local.json .claude/settings.local.json.bak
```

**Git commits** (emergency only):
```bash
git commit --no-verify
```

## Manual Setup

If the installer doesn't work, manually copy the template:

```bash
# Mac/Linux
cp .claude/settings.template.json .claude/settings.local.json

# Windows
copy .claude\settings.template.json .claude\settings.local.json
```

Then edit `.claude/settings.local.json` and change the hook command:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/code-review.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Windows users**: Change `python3` to `python`.

## Suppressing Warnings

Add `# nosec` comment to skip security checks on specific lines:

```python
password = os.getenv("PASSWORD")  # nosec - from environment
```

## Files

```
.claude/
├── settings.template.json   # Template (committed)
├── settings.local.json      # Your settings (gitignored)
└── hooks/
    ├── README.md            # This file
    ├── install.py           # Cross-platform installer
    ├── code-review.py       # Python hook (cross-platform)
    └── code-review.sh       # Bash hook (Mac/Linux)
```

## Troubleshooting

**Hook not running?**
- Verify `.claude/settings.local.json` exists
- Check Claude Code is reading from the right project
- Run `/hooks` in Claude Code to see registered hooks

**Python not found?**
- Windows: Install Python from python.org
- Mac: `brew install python3`
- Linux: `apt install python3`

**Permission denied?**
```bash
chmod +x .claude/hooks/*.py .claude/hooks/*.sh
```
