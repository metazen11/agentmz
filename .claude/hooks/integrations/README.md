# Agent & Editor Integrations

Universal code review tool integration configs for various AI assistants and editors.

## Quick Setup

```bash
# Make the tool available system-wide
chmod +x scripts/code-review
ln -s $(pwd)/scripts/code-review /usr/local/bin/code-review

# Or add to PATH in your shell config
export PATH="$PATH:/path/to/agentmz/scripts"
```

## AI Coding Assistants

### Claude Code
```bash
# Already configured - just run the installer
python3 .claude/hooks/install.py
```

### Aider
```bash
# Add to your .aider.conf.yml or run with flag
aider --lint-cmd "code-review"

# Or create .aider.conf.yml:
# lint-cmd: code-review
```

### Cursor / VS Code
Copy `.vscode/tasks.json` from this directory, or add to existing:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Code Review",
      "type": "shell",
      "command": "code-review",
      "args": ["${file}"],
      "problemMatcher": [],
      "presentation": {"reveal": "always"}
    }
  ]
}
```

### Continue (continue.dev)
Add to `~/.continue/config.json`:
```json
{
  "customCommands": [
    {
      "name": "review",
      "prompt": "Review this code for issues",
      "command": "code-review --json ${file}"
    }
  ]
}
```

### GitHub Copilot CLI
```bash
# Run manually after copilot suggestions
code-review <file>
```

### Cody (Sourcegraph)
Add as VS Code task (same as Cursor/VS Code above).

## Editors

### Vim / Neovim
Add to `.vimrc` or `init.vim`:
```vim
" Auto-review on save
autocmd BufWritePost *.py,*.js,*.ts !code-review %

" Manual review command
command! Review !code-review %
```

### Emacs
Add to `.emacs` or `init.el`:
```elisp
(defun code-review ()
  "Run code review on current buffer."
  (interactive)
  (shell-command (concat "code-review " (buffer-file-name))))

;; Auto-review on save
(add-hook 'after-save-hook
  (lambda ()
    (when (member (file-name-extension buffer-file-name) '("py" "js" "ts"))
      (code-review))))
```

### Sublime Text
Create `code_review.sublime-build`:
```json
{
  "cmd": ["code-review", "$file"],
  "selector": "source.python, source.js, source.ts"
}
```

### JetBrains (PyCharm, WebStorm, etc.)
1. Settings → Tools → External Tools
2. Add new tool:
   - Name: Code Review
   - Program: `code-review`
   - Arguments: `$FilePath$`
   - Working directory: `$ProjectFileDir$`

## CI/CD Integration

### GitHub Actions
```yaml
- name: Code Review
  run: |
    chmod +x scripts/code-review
    git diff --name-only HEAD~1 | xargs -I {} ./scripts/code-review {}
```

### Pre-commit (pre-commit.com)
Add to `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: code-review
        name: Code Review
        entry: scripts/code-review
        language: python
        types: [python, javascript, typescript]
```

## Watch Mode

For real-time feedback while coding:
```bash
# Watch a directory
code-review --watch ./src

# Watch current directory
code-review --watch .
```

## JSON Output

For editor integration that parses output:
```bash
code-review --json myfile.py
```

Output:
```json
{
  "file": "myfile.py",
  "errors": [
    {"line": 10, "message": "Potential SQL injection", "severity": "error"}
  ],
  "warnings": [
    {"line": 5, "message": "Function should be snake_case", "severity": "warning"}
  ],
  "passed": false
}
```
