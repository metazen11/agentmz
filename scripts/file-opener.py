#!/usr/bin/env python3
"""
file-opener.py - Simple HTTP server to open files in the system editor

Runs on the HOST machine (not in Docker) and opens files when requested.
Works on Windows, Mac, and Linux.

Usage:
  python scripts/file-opener.py [--port 8888]

The frontend can then POST to http://localhost:8888/open with JSON:
  {"path": "/path/to/file", "line": 1}
"""

import argparse
import json
import os
import platform
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

DEFAULT_PORT = 8888
WINGET_INSTALL_CMD = ("winget", "install", "-e", "--id", "Microsoft.VisualStudioCode")
WINGET_INSTALL_CMD_WIN = ("cmd.exe", "/c", *WINGET_INSTALL_CMD)

class FileOpenerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging, use our own
        pass

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/install-vscode':
            self.handle_install_vscode()
            return
        elif self.path != '/open':
            self.send_response(404)
            self.end_headers()
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            file_path = data.get('path', '')
            line = data.get('line', 1)

            if not file_path:
                self.send_error(400, 'Missing path')
                return

            # Open the file
            success, message = open_file(file_path, line)

            self.send_response(200 if success else 500)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": success,
                "message": message
            }).encode())

            print(f"{'✓' if success else '✗'} {file_path}" + (f":{line}" if line > 1 else ""))

        except Exception as e:
            self.send_error(500, str(e))

    def handle_install_vscode(self):
        """Install VS Code via platform package manager."""
        try:
            success, message = install_vscode()
            self.send_response(200 if success else 500)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": success,
                "message": message
            }).encode())
            print(f"{'✓' if success else '✗'} VS Code install: {message}")
        except Exception as e:
            self.send_error(500, str(e))


def is_wsl() -> bool:
    """Check if running in WSL (Windows Subsystem for Linux)."""
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except:
        return False


def wsl_to_windows_path(linux_path: str) -> str:
    """Convert WSL path (/mnt/c/...) to Windows path (C:/...)."""
    if linux_path.startswith('/mnt/') and len(linux_path) > 6:
        drive = linux_path[5].upper()
        rest = linux_path[6:].replace('/', '\\')
        return f"{drive}:{rest}"
    return linux_path


def open_file(file_path: str, line: int = 1) -> tuple[bool, str]:
    """Open a file in the system editor."""
    system = platform.system()
    wsl = is_wsl()

    # Check if file exists
    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"

    try:
        # Try VS Code first (cross-platform)
        if is_command_available('code'):
            subprocess.Popen(['code', '--goto', f'{file_path}:{line}'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"Opened in VS Code: {file_path}"

        # Try Cursor
        if is_command_available('cursor'):
            subprocess.Popen(['cursor', '--goto', f'{file_path}:{line}'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"Opened in Cursor: {file_path}"

        # Platform-specific fallbacks
        if system == 'Windows':
            os.startfile(file_path)
            return True, f"Opened with default app: {file_path}"
        elif system == 'Darwin':  # macOS
            subprocess.Popen(['open', file_path])
            return True, f"Opened with default app: {file_path}"
        elif wsl:
            # WSL: Use Windows commands via cmd.exe
            win_path = wsl_to_windows_path(file_path)

            # Try to find VS Code in common Windows locations
            vscode_paths = [
                '/mnt/c/Users/*/AppData/Local/Programs/Microsoft VS Code/bin/code',
                '/mnt/c/Program Files/Microsoft VS Code/bin/code',
            ]

            import glob
            vscode_bin = None
            for pattern in vscode_paths:
                matches = glob.glob(pattern)
                if matches:
                    vscode_bin = matches[0]
                    break

            if vscode_bin:
                subprocess.Popen([vscode_bin, '--goto', f'{file_path}:{line}'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, f"Opened in VS Code: {file_path}"

            # Fallback to Windows default app via cmd.exe start
            result = subprocess.run(
                ['cmd.exe', '/c', 'start', '', win_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if result.returncode == 0:
                return True, f"Opened with Windows default app: {file_path}"

            return False, "VS Code not found. Install with: winget install Microsoft.VisualStudioCode"
        else:  # Linux (non-WSL)
            if is_command_available('xdg-open'):
                subprocess.Popen(['xdg-open', file_path])
                return True, f"Opened with default app: {file_path}"
            return False, "No suitable editor found (xdg-open not available)"

    except Exception as e:
        return False, str(e)


def is_command_available(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['where', cmd], capture_output=True)
        else:
            result = subprocess.run(['which', cmd], capture_output=True)
        return result.returncode == 0
    except:
        return False


def install_vscode() -> tuple[bool, str]:
    """Install VS Code via platform package manager."""
    system = platform.system()
    wsl = is_wsl()

    try:
        if system == 'Windows':
            result = subprocess.run(
                list(WINGET_INSTALL_CMD),
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                return True, "VS Code installed via winget"
            return False, f"winget failed: {result.stderr}"

        elif system == 'Darwin':  # macOS
            result = subprocess.run(
                ['brew', 'install', '--cask', 'visual-studio-code'],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                return True, "VS Code installed via Homebrew"
            return False, f"brew failed: {result.stderr}"

        elif wsl:
            # WSL - install on Windows side
            result = subprocess.run(
                list(WINGET_INSTALL_CMD_WIN),
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                return True, "VS Code installed via winget (Windows)"
            return False, f"winget failed: {result.stderr}"

        else:  # Linux
            # Try snap first
            result = subprocess.run(
                ['sudo', 'snap', 'install', 'code', '--classic'],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                return True, "VS Code installed via snap"
            return False, "Install manually: sudo snap install code --classic"

    except subprocess.TimeoutExpired:
        return False, "Installation timed out"
    except FileNotFoundError as e:
        return False, f"Package manager not found: {e}"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description='File opener HTTP server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Port (default: {DEFAULT_PORT})')
    args = parser.parse_args()

    server = HTTPServer(('127.0.0.1', args.port), FileOpenerHandler)
    print(f"File opener running on http://localhost:{args.port}")
    print("Endpoints:")
    print(f"  GET  /health - Health check")
    print(f"  POST /open   - Open file (JSON: {{\"path\": \"...\", \"line\": 1}})")
    print()
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
        server.shutdown()


if __name__ == '__main__':
    main()
