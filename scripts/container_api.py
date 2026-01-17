#!/usr/bin/env python3
"""
Lightweight Container API Server.

Provides HTTP endpoint for container agent without full Django stack.
Run: python scripts/container_api.py
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.container_service import get_container_service, DOCKER_AVAILABLE

PORT = 8000


class ContainerAPIHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for container API."""

    def _send_json(self, data: dict, status: int = 200):
        """Send JSON response with CORS headers."""
        response = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", len(response))
        self.end_headers()
        self.wfile.write(response)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/api/container/status":
            try:
                service = get_container_service()
                self._send_json({
                    "success": True,
                    "docker": True,
                    "image_exists": service.image_exists(),
                })
            except Exception as e:
                self._send_json({
                    "success": False,
                    "docker": DOCKER_AVAILABLE,
                    "error": str(e),
                })
        elif self.path == "/":
            self._send_json({
                "service": "Container API",
                "endpoints": [
                    "GET /api/container/status",
                    "POST /api/container/execute",
                    "POST /api/container/build",
                ],
            })
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({"success": False, "error": "Invalid JSON"}, 400)
            return

        if self.path == "/api/container/execute":
            workspace = data.get("workspace")
            prompt = data.get("prompt")

            if not workspace or not prompt:
                self._send_json({
                    "success": False,
                    "error": "Missing workspace or prompt",
                }, 400)
                return

            try:
                service = get_container_service()
                result = service.run_coding_task(
                    workspace_path=workspace,
                    prompt=prompt,
                    model=data.get("model"),
                    context_size=data.get("context_size"),
                    max_tokens=data.get("max_tokens"),
                )
                self._send_json(result)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        elif self.path == "/api/container/build":
            try:
                service = get_container_service()
                result = service.build_image()
                self._send_json(result)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        else:
            self._send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    """Start the API server."""
    if not DOCKER_AVAILABLE:
        print("ERROR: Docker SDK not available. Install with: pip install docker")
        sys.exit(1)

    try:
        service = get_container_service()
        print(f"Docker: Connected")
        print(f"Image {service.IMAGE_NAME}: {'found' if service.image_exists() else 'NOT FOUND - run /api/container/build'}")
    except Exception as e:
        print(f"Docker error: {e}")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), ContainerAPIHandler)
    print(f"\nContainer API running on http://localhost:{PORT}")
    print("Endpoints:")
    print("  GET  /api/container/status")
    print("  POST /api/container/execute  {workspace, prompt}")
    print("  POST /api/container/build")
    print("\nPress Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
