#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wrapper="${script_dir}/wrapper_init.sh"

show_help() {
  cat <<'EOF'
Usage:
  ./aicoder_install.sh

Installs aider (if missing) and registers the aicoder wrapper in shell rc files.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
  exit 0
fi

if ! command -v aider >/dev/null 2>&1; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to install aider." >&2
    exit 1
  fi
  if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "pip is required to install aider. Install pip and re-run." >&2
    exit 1
  fi
  python3 -m pip install --user aider-chat
fi

if [ ! -f "$wrapper" ]; then
  echo "wrapper_init.sh not found at ${wrapper}" >&2
  exit 1
fi

add_source_line() {
  local rc_file="$1"
  local line="source ${wrapper}"
  if [ -f "$rc_file" ]; then
    if ! rg -F "$line" "$rc_file" >/dev/null 2>&1; then
      printf '\n# aicoder wrapper\n%s\n' "$line" >> "$rc_file"
    fi
  else
    printf '# aicoder wrapper\n%s\n' "$line" > "$rc_file"
  fi
}

add_source_line "${HOME}/.bashrc"
add_source_line "${HOME}/.zshrc"

echo "aicoder installed. Run: source ~/.bashrc"
