#!/usr/bin/env bash
#
# install_aider.sh - Install aider-chat and register the agent command
#
# NOTE: This script is now integrated into install.sh
#       You can use: ./install.sh --aider --agent  (or --all)
#       This standalone script is kept for backward compatibility.
#
# This script uses the official aider installer which:
#   1. Installs Python 3.12 if needed (via uv)
#   2. Installs aider-chat
#   3. Then registers the 'agent' command
#
# Usage: ./install_aider.sh [--skip-agent] [--pip]
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
USE_PIP=false
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
  --pip           Use pip instead of official installer (fallback)
  --verbose, -v   Show verbose output
  --help, -h      Show this help message

Examples:
  ./install_aider.sh              # Full installation (recommended)
  ./install_aider.sh --skip-agent # Only install aider
  ./install_aider.sh --pip        # Use pip fallback method
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
      --pip)
        USE_PIP=true
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
# Install aider using official one-liner
#######################################
install_aider_official() {
  info "Installing aider using official installer..."
  info "This will install aider and Python 3.12 if needed"
  echo ""

  # Check if curl is available
  if ! command_exists curl; then
    error "curl is required for official installer"
    return 1
  fi

  # Run official installer
  if curl -LsSf https://aider.chat/install.sh | sh; then
    success "Official aider installer completed"
    return 0
  else
    error "Official installer failed"
    return 1
  fi
}

#######################################
# Install aider using pip (fallback)
#######################################
install_aider_pip() {
  info "Installing aider using pip..."

  local python_cmd=""

  # Find Python
  if command_exists python3; then
    python_cmd="python3"
  elif command_exists python; then
    if python --version 2>&1 | grep -q "Python 3"; then
      python_cmd="python"
    fi
  fi

  if [[ -z "$python_cmd" ]]; then
    error "Python 3 is required but not found"
    error "Install Python 3 or use: ./install_aider.sh (without --pip)"
    return 1
  fi

  # Check pip
  if ! $python_cmd -m pip --version >/dev/null 2>&1; then
    error "pip is required. Install with: $python_cmd -m ensurepip --upgrade"
    return 1
  fi

  # Install aider
  if $python_cmd -m pip install --user aider-chat; then
    success "aider-chat installed via pip"
    return 0
  else
    warn "User install failed, trying without --user..."
    if $python_cmd -m pip install aider-chat; then
      success "aider-chat installed via pip (system)"
      return 0
    fi
  fi

  error "pip installation failed"
  return 1
}

#######################################
# Install aider-chat
#######################################
install_aider() {
  # Check if already installed
  if command_exists aider; then
    local current_version
    current_version=$(aider --version 2>/dev/null || echo "unknown")
    success "aider is already installed: $current_version"
    return 0
  fi

  # Use pip method if requested
  if [[ "$USE_PIP" == "true" ]]; then
    install_aider_pip
    return $?
  fi

  # Try official installer first
  if install_aider_official; then
    # Verify installation
    # The official installer may put aider in ~/.local/bin
    if ! command_exists aider; then
      export PATH="$HOME/.local/bin:$PATH"
    fi

    if command_exists aider; then
      local version
      version=$(aider --version 2>/dev/null || echo "installed")
      success "aider ready: $version"
      return 0
    fi
  fi

  # Fallback to pip
  warn "Official installer didn't work, trying pip fallback..."
  if install_aider_pip; then
    # Check PATH
    if ! command_exists aider; then
      export PATH="$HOME/.local/bin:$PATH"
    fi

    if command_exists aider; then
      local version
      version=$(aider --version 2>/dev/null || echo "installed")
      success "aider ready: $version"
      return 0
    fi
  fi

  error "Could not install aider"
  error "Try manually: curl -LsSf https://aider.chat/install.sh | sh"
  return 1
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

  # Check for curl (needed for official installer)
  if ! command_exists curl; then
    warn "curl not found - will try pip method"
    USE_PIP=true
  fi

  # Install aider
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
