#!/bin/bash
# open-file.sh - Open a file in the configured editor
#
# Usage: ./scripts/open-file.sh <file_path> [line_number]
#
# Supports: VS Code, Cursor, Notepad++, Sublime, vim, or system default
# Configure via EDITOR_CMD environment variable in .env

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env if exists
if [ -f "$PROJECT_ROOT/.env" ]; then
  source "$PROJECT_ROOT/.env"
fi

FILE_PATH="$1"
LINE_NUM="${2:-1}"

if [ -z "$FILE_PATH" ]; then
  echo "Usage: $0 <file_path> [line_number]"
  exit 1
fi

# Detect OS/environment
detect_editor() {
  # Check configured editor first
  if [ -n "$EDITOR_CMD" ]; then
    echo "$EDITOR_CMD"
    return
  fi

  # WSL detection
  if grep -qi microsoft /proc/version 2>/dev/null; then
    # Try VS Code
    if command -v code &>/dev/null; then
      echo "code --goto"
      return
    fi
    # Try Cursor
    if command -v cursor &>/dev/null; then
      echo "cursor --goto"
      return
    fi
    # Try Windows VS Code via cmd
    if cmd.exe /c "where code" &>/dev/null; then
      echo "cmd.exe /c code --goto"
      return
    fi
    # Try Notepad++
    if [ -f "/mnt/c/Program Files/Notepad++/notepad++.exe" ]; then
      echo "'/mnt/c/Program Files/Notepad++/notepad++.exe' -n"
      return
    fi
    # Fallback to Windows notepad
    echo "notepad.exe"
    return
  fi

  # macOS
  if [ "$(uname)" = "Darwin" ]; then
    if command -v code &>/dev/null; then
      echo "code --goto"
    elif command -v cursor &>/dev/null; then
      echo "cursor --goto"
    elif command -v subl &>/dev/null; then
      echo "subl"
    else
      echo "open -t"
    fi
    return
  fi

  # Linux
  if command -v code &>/dev/null; then
    echo "code --goto"
  elif command -v cursor &>/dev/null; then
    echo "cursor --goto"
  elif command -v subl &>/dev/null; then
    echo "subl"
  elif [ -n "$VISUAL" ]; then
    echo "$VISUAL"
  elif [ -n "$EDITOR" ]; then
    echo "$EDITOR"
  else
    echo "xdg-open"
  fi
}

EDITOR="$(detect_editor)"

# Convert WSL path to Windows path if needed
if grep -qi microsoft /proc/version 2>/dev/null; then
  if [[ "$FILE_PATH" == /mnt/* ]]; then
    # Already a Windows-accessible path
    :
  elif [[ "$FILE_PATH" == /* ]]; then
    # Convert Linux path to Windows path
    FILE_PATH="$(wslpath -w "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")"
  fi
fi

# Open the file
case "$EDITOR" in
  *"--goto"*)
    # VS Code / Cursor style: file:line
    eval $EDITOR "\"$FILE_PATH:$LINE_NUM\""
    ;;
  *"-n"*)
    # Notepad++ style: -n<line>
    eval $EDITOR"$LINE_NUM" "\"$FILE_PATH\""
    ;;
  *)
    eval $EDITOR "\"$FILE_PATH\""
    ;;
esac
