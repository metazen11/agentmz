#!/usr/bin/env bash
#
# install_aider.sh - Install aider-chat and register the agent command
#
# This script:
#   1. Checks prerequisites (python3, pip)
#   2. Installs aider-chat via pip
#   3. Verifies the installation
#   4. Runs install_agent.sh to register the 'agent' command
#
# Usage: ./install_aider.sh [--skip-agent]
#

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Flags
SKIP_AGENT=false
VERBOSE=false

#######################################
# Print colored message
#######################################
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

Install aider-chat and register the 'agent' command.

Options:
  --skip-agent    Skip agent command registration (only install aider)
  --verbose, -v   Show verbose output
  --help, -h      Show this help message

Examples:
  ./install_aider.sh              # Full installation
  ./install_aider.sh --skip-agent # Only install aider
EOF
}

#######################################
# Parse arguments
#######################################
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-agent)
        SKIP_AGENT=true
        shift
        ;;
      --verbose|-v)
        VERBOSE=true
        shift
        ;;
      --help|-h)
        show_help
        exit 0
        ;;
      *)
        warn "Unknown option: $1"
        shift
        ;;
    esac
  done
}

#######################################
# Check if command exists
#######################################
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

#######################################
# Get Python command (python3 or python)
#######################################
get_python_cmd() {
  if command_exists python3; then
    echo "python3"
  elif command_exists python; then
    # Verify it's Python 3
    if python --version 2>&1 | grep -q "Python 3"; then
      echo "python"
    else
      return 1
    fi
  else
    return 1
  fi
}

#######################################
# Check prerequisites
#######################################
check_prerequisites() {
  info "Checking prerequisites..."

  local errors=0

  # Check Python
  local python_cmd
  if ! python_cmd=$(get_python_cmd); then
    error "Python 3 is required but not found"
    error "Install Python 3: https://www.python.org/downloads/"
    ((errors++))
  else
    local py_version
    py_version=$($python_cmd --version 2>&1)
    success "Found $py_version"
  fi

  # Check pip
  if [[ -n "${python_cmd:-}" ]]; then
    if ! $python_cmd -m pip --version >/dev/null 2>&1; then
      error "pip is required but not found"
      error "Install pip: $python_cmd -m ensurepip --upgrade"
      ((errors++))
    else
      local pip_version
      pip_version=$($python_cmd -m pip --version 2>&1 | head -1)
      success "Found pip: $pip_version"
    fi
  fi

  # Check git (optional but recommended)
  if ! command_exists git; then
    warn "git not found - some aider features may be limited"
  else
    success "Found git: $(git --version)"
  fi

  if [[ $errors -gt 0 ]]; then
    error "Prerequisites check failed with $errors error(s)"
    return 1
  fi

  success "All prerequisites satisfied"
  return 0
}

#######################################
# Install aider-chat
#######################################
install_aider() {
  local python_cmd
  python_cmd=$(get_python_cmd)

  # Check if already installed
  if command_exists aider; then
    local current_version
    current_version=$(aider --version 2>/dev/null || echo "unknown")
    success "aider is already installed: $current_version"

    info "Checking for updates..."
    if $python_cmd -m pip install --user --upgrade aider-chat 2>/dev/null; then
      local new_version
      new_version=$(aider --version 2>/dev/null || echo "unknown")
      if [[ "$current_version" != "$new_version" ]]; then
        success "Updated aider to: $new_version"
      else
        success "aider is up to date"
      fi
    else
      warn "Could not check for updates (non-fatal)"
    fi
    return 0
  fi

  info "Installing aider-chat..."

  # Try user install first (no sudo required)
  if $python_cmd -m pip install --user aider-chat; then
    success "aider-chat installed successfully (user install)"
  else
    warn "User install failed, trying system install..."

    # Try without --user
    if $python_cmd -m pip install aider-chat; then
      success "aider-chat installed successfully (system install)"
    else
      error "Failed to install aider-chat"
      error "Try manually: $python_cmd -m pip install aider-chat"
      return 1
    fi
  fi

  # Verify installation
  if ! command_exists aider; then
    # Check if it's in user bin
    local user_bin="$HOME/.local/bin"
    if [[ -f "$user_bin/aider" ]]; then
      warn "aider installed to $user_bin but not in PATH"
      warn "Add to your shell rc file: export PATH=\"\$HOME/.local/bin:\$PATH\""

      # Try to add to PATH for current session
      export PATH="$user_bin:$PATH"

      if command_exists aider; then
        success "aider is now available in current session"
      fi
    else
      error "aider command not found after installation"
      error "You may need to restart your shell or add ~/.local/bin to PATH"
      return 1
    fi
  fi

  local version
  version=$(aider --version 2>/dev/null || echo "installed")
  success "aider ready: $version"
  return 0
}

#######################################
# Run agent registration
#######################################
register_agent() {
  info "Registering 'agent' command..."

  local install_script="$SCRIPT_DIR/agent_alias_install.sh"

  # Check for install script
  if [[ ! -f "$install_script" ]]; then
    # Try alternative name
    install_script="$SCRIPT_DIR/install_agent.sh"
    if [[ ! -f "$install_script" ]]; then
      warn "Agent install script not found"
      warn "You can still use aider directly or run: source $SCRIPT_DIR/wrapper_init.sh"
      return 0
    fi
  fi

  # Make executable
  chmod +x "$install_script" 2>/dev/null || true

  # Run the agent registration
  if bash "$install_script"; then
    success "Agent command registered"
  else
    warn "Agent registration had issues (non-fatal)"
    warn "You can manually run: $install_script"
  fi

  return 0
}

#######################################
# Post-install instructions
#######################################
show_post_install() {
  echo ""
  echo "============================================"
  echo -e "${GREEN}Installation Complete!${NC}"
  echo "============================================"
  echo ""
  echo "To start using aider:"
  echo ""
  echo "  1. Reload your shell:"
  echo "     source ~/.bashrc  # or ~/.zshrc"
  echo ""
  echo "  2. Run the agent command:"
  echo "     agent                    # Interactive mode"
  echo "     agent -m 'fix the bug'   # With prompt"
  echo "     agent --yolo -m 'task'   # Auto-approve mode"
  echo ""
  echo "  Or use aider directly:"
  echo "     aider"
  echo ""
  echo "Documentation: $SCRIPT_DIR/README_AGENT.md"
  echo ""
}

#######################################
# Main
#######################################
main() {
  parse_args "$@"

  echo ""
  echo "=========================================="
  echo "  Aider Installation Script"
  echo "=========================================="
  echo ""

  # Step 1: Check prerequisites
  if ! check_prerequisites; then
    error "Please install missing prerequisites and try again"
    exit 1
  fi

  echo ""

  # Step 2: Install aider
  if ! install_aider; then
    error "Aider installation failed"
    exit 1
  fi

  echo ""

  # Step 3: Register agent command (unless skipped)
  if [[ "$SKIP_AGENT" == "false" ]]; then
    register_agent
  else
    info "Skipping agent command registration (--skip-agent)"
  fi

  # Show post-install instructions
  show_post_install

  exit 0
}

# Run main
main "$@"
