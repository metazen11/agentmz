#!/usr/bin/env bash
#
# install_agent.sh - Register the 'agent' command in shell rc files
#
# This script:
#   1. Sets AGENTMZ_DIR environment variable
#   2. Sources wrapper_init.sh for the 'agent' function
#   3. Updates ~/.bashrc and ~/.zshrc
#
# Usage: ./install_agent.sh [--uninstall]
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="${SCRIPT_DIR}/wrapper_init.sh"

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

#######################################
# Show help
#######################################
show_help() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Register the 'agent' command in your shell configuration.

Options:
  --uninstall     Remove agent configuration from shell rc files
  --check         Check current installation status
  --help, -h      Show this help message

After installation, run: source ~/.bashrc
Then type: agent
EOF
}

#######################################
# Check if wrapper exists
#######################################
check_wrapper() {
  if [[ ! -f "$WRAPPER" ]]; then
    error "wrapper_init.sh not found at: $WRAPPER"
    error "Make sure you're running this from the agentmz directory"
    return 1
  fi
  return 0
}

#######################################
# Add configuration to rc file
#######################################
add_to_rc() {
  local rc_file="$1"
  local env_export="export AGENTMZ_DIR=\"${SCRIPT_DIR}\""
  local source_line="source \"\${AGENTMZ_DIR}/wrapper_init.sh\""

  # Skip if file doesn't exist and it's not bashrc
  if [[ ! -f "$rc_file" ]]; then
    if [[ "$rc_file" == *".bashrc" ]]; then
      # Create bashrc if it doesn't exist
      touch "$rc_file" 2>/dev/null || {
        warn "Could not create $rc_file"
        return 1
      }
    else
      # Skip other rc files if they don't exist
      return 0
    fi
  fi

  # Check if already configured
  if grep -q "AGENTMZ_DIR" "$rc_file" 2>/dev/null; then
    info "Updating existing configuration in $rc_file"

    # Create temp file
    local tmp_file
    tmp_file=$(mktemp 2>/dev/null) || tmp_file="/tmp/rc_tmp_$$"

    # Remove old entries
    grep -v "AGENTMZ_DIR" "$rc_file" | grep -v "wrapper_init.sh" | grep -v "# agentmz" > "$tmp_file" 2>/dev/null || true

    # Replace original
    if mv "$tmp_file" "$rc_file" 2>/dev/null; then
      : # success
    else
      warn "Could not update $rc_file - trying append only"
      rm -f "$tmp_file" 2>/dev/null
    fi
  fi

  # Append new configuration
  {
    echo ""
    echo "# agentmz - AI coding assistant"
    echo "$env_export"
    echo "$source_line"
  } >> "$rc_file" 2>/dev/null || {
    error "Could not write to $rc_file"
    return 1
  }

  success "Updated $rc_file"
  return 0
}

#######################################
# Remove configuration from rc file
#######################################
remove_from_rc() {
  local rc_file="$1"

  if [[ ! -f "$rc_file" ]]; then
    return 0
  fi

  if ! grep -q "AGENTMZ_DIR" "$rc_file" 2>/dev/null; then
    info "No agent configuration found in $rc_file"
    return 0
  fi

  # Create temp file
  local tmp_file
  tmp_file=$(mktemp 2>/dev/null) || tmp_file="/tmp/rc_tmp_$$"

  # Remove entries
  grep -v "AGENTMZ_DIR" "$rc_file" | grep -v "wrapper_init.sh" | grep -v "# agentmz" > "$tmp_file" 2>/dev/null || true

  if mv "$tmp_file" "$rc_file" 2>/dev/null; then
    success "Removed agent configuration from $rc_file"
  else
    error "Could not update $rc_file"
    rm -f "$tmp_file" 2>/dev/null
    return 1
  fi

  return 0
}

#######################################
# Check installation status
#######################################
check_status() {
  echo ""
  info "Checking agent installation status..."
  echo ""

  local installed=false

  # Check AGENTMZ_DIR
  if [[ -n "${AGENTMZ_DIR:-}" ]]; then
    success "AGENTMZ_DIR is set: $AGENTMZ_DIR"
    installed=true
  else
    warn "AGENTMZ_DIR is not set in current shell"
  fi

  # Check if agent function exists
  if type agent >/dev/null 2>&1; then
    success "agent command is available"
    installed=true
  else
    warn "agent command is not available in current shell"
  fi

  # Check rc files
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [[ -f "$rc" ]] && grep -q "AGENTMZ_DIR" "$rc" 2>/dev/null; then
      success "Configuration found in $rc"
      installed=true
    fi
  done

  # Check aider
  if command -v aider >/dev/null 2>&1; then
    success "aider is installed: $(aider --version 2>/dev/null || echo 'unknown version')"
  else
    warn "aider is not installed or not in PATH"
  fi

  echo ""
  if [[ "$installed" == "true" ]]; then
    info "Agent appears to be installed. Run 'source ~/.bashrc' to reload."
  else
    info "Agent is not installed. Run: ./install_agent.sh"
  fi
}

#######################################
# Install agent
#######################################
do_install() {
  echo ""
  info "Installing agent command..."
  echo ""

  if ! check_wrapper; then
    exit 1
  fi

  local errors=0

  # Update bashrc
  if ! add_to_rc "$HOME/.bashrc"; then
    ((errors++))
  fi

  # Update zshrc (if exists or user uses zsh)
  if [[ -f "$HOME/.zshrc" ]] || [[ "$SHELL" == *"zsh"* ]]; then
    if ! add_to_rc "$HOME/.zshrc"; then
      ((errors++))
    fi
  fi

  echo ""

  if [[ $errors -gt 0 ]]; then
    warn "Installation completed with $errors warning(s)"
  else
    success "Installation complete!"
  fi

  echo ""
  echo "AGENTMZ_DIR=$SCRIPT_DIR"
  echo ""
  echo "Next steps:"
  echo "  1. Run: source ~/.bashrc"
  echo "  2. Type: agent"
  echo ""
}

#######################################
# Uninstall agent
#######################################
do_uninstall() {
  echo ""
  info "Removing agent command configuration..."
  echo ""

  remove_from_rc "$HOME/.bashrc"
  remove_from_rc "$HOME/.zshrc"

  echo ""
  success "Agent configuration removed"
  echo ""
  echo "Note: aider-chat is still installed. To remove it:"
  echo "  pip uninstall aider-chat"
  echo ""
}

#######################################
# Main
#######################################
main() {
  case "${1:-}" in
    --help|-h)
      show_help
      exit 0
      ;;
    --uninstall)
      do_uninstall
      exit 0
      ;;
    --check)
      check_status
      exit 0
      ;;
    *)
      do_install
      exit 0
      ;;
  esac
}

main "$@"
