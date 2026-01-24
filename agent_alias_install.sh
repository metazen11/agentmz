#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wrapper="${script_dir}/wrapper_init.sh"

show_help() {
  cat <<'EOF'
Usage:
  ./agent_alias_install.sh

Installs aider (if missing) and registers the 'agent' command in shell rc files.
Also sets AGENTMZ_DIR environment variable pointing to the project root.

After installation, type 'agent' to start an AI coding assistant.
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
  echo "Installing aider-chat..."
  python3 -m pip install --user aider-chat
fi

if [ ! -f "$wrapper" ]; then
  echo "wrapper_init.sh not found at ${wrapper}" >&2
  exit 1
fi

add_to_rc() {
  local rc_file="$1"
  local env_export="export AGENTMZ_DIR=\"${script_dir}\""
  local source_line="source \"\${AGENTMZ_DIR}/wrapper_init.sh\""

  if [ -f "$rc_file" ]; then
    # Remove old entries if present
    grep -v "AGENTMZ_DIR" "$rc_file" | grep -v "wrapper_init.sh" > "${rc_file}.tmp" 2>/dev/null || true
    mv "${rc_file}.tmp" "$rc_file"
  fi

  # Add new entries
  {
    echo ""
    echo "# agentmz - AI coding assistant"
    echo "$env_export"
    echo "$source_line"
  } >> "$rc_file"

  echo "Updated $rc_file"
}

add_to_rc "${HOME}/.bashrc"
add_to_rc "${HOME}/.zshrc"

echo ""
echo "Installation complete!"
echo "AGENTMZ_DIR=${script_dir}"
echo ""
echo "Run: source ~/.bashrc"
echo "Then type: agent"
