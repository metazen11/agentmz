#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

has_cmd() {
    command -v "$1" >/dev/null 2>&1
}

run_js() {
    exec "$1" "$SCRIPT_DIR/smart_startup.js" "$@"
}

if has_cmd bun; then
    run_js bun "$@"
fi

if has_cmd node; then
    run_js node "$@"
fi

echo "Node or Bun not found. Attempting to install Node..."

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    SUDO="sudo"
else
    SUDO=""
fi

OS_NAME="$(uname -s)"

case "$OS_NAME" in
    Darwin)
        if has_cmd brew; then
            echo "Installing Node via Homebrew..."
            $SUDO brew install node
        else
            echo "Homebrew not found. Please install Node from https://nodejs.org or install Homebrew, then rerun."
            exit 1
        fi
        ;;
    Linux)
        if has_cmd apt-get; then
            echo "Installing Node via apt-get..."
            $SUDO apt-get update
            $SUDO apt-get install -y nodejs npm
        elif has_cmd dnf; then
            echo "Installing Node via dnf..."
            $SUDO dnf install -y nodejs npm
        elif has_cmd yum; then
            echo "Installing Node via yum..."
            $SUDO yum install -y nodejs npm
        elif has_cmd pacman; then
            echo "Installing Node via pacman..."
            $SUDO pacman -Sy --noconfirm nodejs npm
        elif has_cmd zypper; then
            echo "Installing Node via zypper..."
            $SUDO zypper install -y nodejs npm
        elif has_cmd apk; then
            echo "Installing Node via apk..."
            $SUDO apk add --no-cache nodejs npm
        else
            echo "No supported package manager found. Please install Node from https://nodejs.org and rerun."
            exit 1
        fi
        ;;
    MINGW*|MSYS*|CYGWIN*)
        echo "Windows detected. Please install Node via winget:"
        echo "  winget install OpenJS.NodeJS.LTS"
        exit 1
        ;;
    *)
        echo "Unsupported OS. Please install Node from https://nodejs.org and rerun."
        exit 1
        ;;
esac

if has_cmd node; then
    run_js node "$@"
fi

echo "Node install did not complete successfully. Please install Node manually and rerun."
exit 1
