#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_ROOT/venv"

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  cat <<'EOM'
This script must be sourced so that the activated environment affects your session.
Run it like:
  . scripts/activate_venv.sh
or
  source scripts/activate_venv.sh
EOM
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Virtual environment not found in $VENV_DIR; create it with: python3 -m venv venv"
  return 1
fi

source "$VENV_DIR/bin/activate"
echo "Activated virtualenv in $VENV_DIR"
