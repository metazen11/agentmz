"""
Container Manager - Dynamically start/stop containers using Docker SDK.

This module manages the v2 coding agent containers:
- wfhub-v2-ollama: Local LLM with shared model cache
- wfhub-v2-aider-api: Coding tools API with workspace mounted

Usage:
    from container_manager import ContainerManager

    manager = ContainerManager(workspace_path="/path/to/workspace")
    manager.start_all()  # Starts all containers
    manager.stop_all()   # Stops all containers
"""

import os
import time
import docker
from pathlib import Path
from typing import Optional


class ContainerManager:
    """Manages Docker containers for v2 coding agent stack."""

    # Container names
    OLLAMA_CONTAINER = "wfhub-v2-ollama"
    AIDER_API_CONTAINER = "wfhub-v2-aider-api"

    # Default ports
    OLLAMA_HOST_PORT = 11435
    OLLAMA_CONTAINER_PORT = 11434
    AIDER_API_PORT = 8001

    # Images
    OLLAMA_IMAGE = "ollama/ollama:latest"

    def __init__(self, workspace_path: str = None, model: str = None):
        """
        Initialize the container manager.

        Args:
            workspace_path: Path to workspace directory to mount
            model: LLM model name (default from env or qwen3:1.7b)
        """
        self.client = docker.from_env()
        self.workspace_path = workspace_path or os.path.join(
            os.path.dirname(__file__), "workspaces", "poc"
        )
        self.model = model or os.environ.get("AGENT_MODEL", "qwen3:1.7b")

        # Get the v2 directory for building aider-api
        self.v2_dir = Path(__file__).parent.resolve()

        # Check if workspace exists
        if not os.path.isdir(self.workspace_path):
            raise ValueError(f"Workspace not found: {self.workspace_path}")

    def _get_container(self, name: str) -> Optional[docker.models.containers.Container]:
        """Get container by name if it exists."""
        try:
            return self.client.containers.get(name)
        except docker.errors.NotFound:
            return None

    def _wait_for_url(self, url: str, timeout: int = 60) -> bool:
        """Wait for a URL to respond."""
        import urllib.request
        import urllib.error

        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, Exception):
                pass
            time.sleep(1)
        return False

    def start_ollama(self) -> bool:
        """Start or ensure Ollama container is running."""
        print(f"[MANAGER] Starting {self.OLLAMA_CONTAINER}...")

        container = self._get_container(self.OLLAMA_CONTAINER)

        if container:
            if container.status == "running":
                print(f"[MANAGER] {self.OLLAMA_CONTAINER} already running")
                return True
            else:
                print(f"[MANAGER] Starting stopped container...")
                container.start()
        else:
            # Create new container with shared model volume
            print(f"[MANAGER] Creating new Ollama container...")
            container = self.client.containers.run(
                self.OLLAMA_IMAGE,
                name=self.OLLAMA_CONTAINER,
                hostname=self.OLLAMA_CONTAINER,
                ports={f"{self.OLLAMA_CONTAINER_PORT}/tcp": self.OLLAMA_HOST_PORT},
                volumes={
                    "wfhub_ollama_data": {"bind": "/root/.ollama", "mode": "rw"}
                },
                detach=True,
                remove=False,  # Keep container for reuse
            )

        # Wait for Ollama to be ready
        print(f"[MANAGER] Waiting for Ollama at http://localhost:{self.OLLAMA_HOST_PORT}...")
        if not self._wait_for_url(f"http://localhost:{self.OLLAMA_HOST_PORT}/api/tags", timeout=60):
            print(f"[MANAGER] ERROR: Ollama did not start in time")
            return False

        print(f"[MANAGER] Ollama ready!")
        return True

    def ensure_model(self) -> bool:
        """Ensure the required model is available, pull if needed."""
        import urllib.request
        import json

        print(f"[MANAGER] Checking for model: {self.model}")

        # Check if model exists
        try:
            req = urllib.request.Request(f"http://localhost:{self.OLLAMA_HOST_PORT}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]

                if self.model in models:
                    print(f"[MANAGER] Model {self.model} already available")
                    return True

                # Check partial match
                for m in models:
                    if self.model.split(":")[0] in m:
                        print(f"[MANAGER] Found compatible model: {m}")
                        return True
        except Exception as e:
            print(f"[MANAGER] Error checking models: {e}")
            return False

        # Pull the model
        print(f"[MANAGER] Pulling model {self.model}...")
        container = self._get_container(self.OLLAMA_CONTAINER)
        if container:
            exit_code, output = container.exec_run(f"ollama pull {self.model}")
            if exit_code == 0:
                print(f"[MANAGER] Model {self.model} pulled successfully")
                return True
            else:
                print(f"[MANAGER] Error pulling model: {output.decode()}")
                return False
        return False

    def start_aider_api(self) -> bool:
        """Start or ensure aider-api container is running."""
        print(f"[MANAGER] Starting {self.AIDER_API_CONTAINER}...")

        container = self._get_container(self.AIDER_API_CONTAINER)

        if container:
            if container.status == "running":
                print(f"[MANAGER] {self.AIDER_API_CONTAINER} already running")
                # Check if workspace mount matches
                return True
            else:
                # Remove stopped container to recreate with correct mounts
                print(f"[MANAGER] Removing stopped container to recreate...")
                container.remove()

        # Build the image if needed
        image_name = "wfhub-v2-aider-api"
        dockerfile_path = self.v2_dir / "docker" / "Dockerfile.aider-api"

        if not dockerfile_path.exists():
            print(f"[MANAGER] ERROR: Dockerfile not found: {dockerfile_path}")
            return False

        print(f"[MANAGER] Building aider-api image...")
        try:
            image, logs = self.client.images.build(
                path=str(self.v2_dir),
                dockerfile=str(dockerfile_path.relative_to(self.v2_dir)),
                tag=image_name,
                rm=True,
            )
            for log in logs:
                if "stream" in log:
                    line = log["stream"].strip()
                    if line:
                        print(f"  {line}")
        except docker.errors.BuildError as e:
            print(f"[MANAGER] ERROR building image: {e}")
            return False

        # Resolve workspace to absolute path
        workspace_abs = os.path.abspath(self.workspace_path)
        workspaces_dir = os.path.dirname(workspace_abs)

        print(f"[MANAGER] Creating aider-api container...")
        print(f"[MANAGER] Mounting {workspaces_dir} -> /workspaces")
        print(f"[MANAGER] Mounting {self.v2_dir} -> /v2")

        container = self.client.containers.run(
            image_name,
            name=self.AIDER_API_CONTAINER,
            hostname=self.AIDER_API_CONTAINER,
            ports={f"{self.AIDER_API_PORT}/tcp": self.AIDER_API_PORT},
            environment={
                "OLLAMA_API_BASE": f"http://{self.OLLAMA_CONTAINER}:{self.OLLAMA_CONTAINER_PORT}",
                "PORT": str(self.AIDER_API_PORT),
                "AIDER_MODEL": f"ollama_chat/{self.model}",
                "AGENT_MODEL": self.model,
                "DEFAULT_WORKSPACE": os.path.basename(self.workspace_path),
                "WORKSPACES_DIR": "/workspaces",
            },
            volumes={
                workspaces_dir: {"bind": "/workspaces", "mode": "rw"},
                str(self.v2_dir): {"bind": "/v2", "mode": "rw"},
            },
            working_dir="/workspaces",
            network_mode="bridge",
            links={self.OLLAMA_CONTAINER: self.OLLAMA_CONTAINER},
            detach=True,
            remove=False,
        )

        # Wait for aider-api to be ready
        print(f"[MANAGER] Waiting for aider-api at http://localhost:{self.AIDER_API_PORT}...")
        if not self._wait_for_url(f"http://localhost:{self.AIDER_API_PORT}/health", timeout=60):
            print(f"[MANAGER] ERROR: aider-api did not start in time")
            # Show logs
            logs = container.logs(tail=20).decode()
            print(f"[MANAGER] Container logs:\n{logs}")
            return False

        print(f"[MANAGER] aider-api ready!")
        return True

    def start_all(self) -> bool:
        """Start all containers in order."""
        print(f"[MANAGER] Starting v2 coding agent stack...")
        print(f"[MANAGER] Workspace: {self.workspace_path}")
        print(f"[MANAGER] Model: {self.model}")

        # Start Ollama
        if not self.start_ollama():
            return False

        # Ensure model is available
        if not self.ensure_model():
            return False

        # Start aider-api
        if not self.start_aider_api():
            return False

        print(f"\n[MANAGER] All containers started successfully!")
        print(f"[MANAGER] Ollama: http://localhost:{self.OLLAMA_HOST_PORT}")
        print(f"[MANAGER] Aider API: http://localhost:{self.AIDER_API_PORT}")
        return True

    def stop_all(self):
        """Stop all containers."""
        print(f"[MANAGER] Stopping v2 containers...")

        for name in [self.AIDER_API_CONTAINER, self.OLLAMA_CONTAINER]:
            container = self._get_container(name)
            if container and container.status == "running":
                print(f"[MANAGER] Stopping {name}...")
                container.stop(timeout=10)

        print(f"[MANAGER] All containers stopped")

    def status(self) -> dict:
        """Get status of all containers."""
        result = {}
        for name in [self.OLLAMA_CONTAINER, self.AIDER_API_CONTAINER]:
            container = self._get_container(name)
            if container:
                result[name] = container.status
            else:
                result[name] = "not found"
        return result

    def cleanup(self):
        """Remove all containers (but not volumes)."""
        print(f"[MANAGER] Cleaning up containers...")

        for name in [self.AIDER_API_CONTAINER, self.OLLAMA_CONTAINER]:
            container = self._get_container(name)
            if container:
                print(f"[MANAGER] Removing {name}...")
                if container.status == "running":
                    container.stop(timeout=10)
                container.remove()

        print(f"[MANAGER] Cleanup complete")


def main():
    """CLI for container manager."""
    import argparse

    parser = argparse.ArgumentParser(description="v2 Container Manager")
    parser.add_argument("command", choices=["start", "stop", "status", "cleanup"],
                        help="Command to run")
    parser.add_argument("--workspace", "-w", default=None,
                        help="Path to workspace (default: workspaces/poc)")
    parser.add_argument("--model", "-m", default=None,
                        help="LLM model (default: qwen3:1.7b)")

    args = parser.parse_args()

    manager = ContainerManager(
        workspace_path=args.workspace,
        model=args.model
    )

    if args.command == "start":
        success = manager.start_all()
        exit(0 if success else 1)
    elif args.command == "stop":
        manager.stop_all()
    elif args.command == "status":
        status = manager.status()
        for name, state in status.items():
            print(f"{name}: {state}")
    elif args.command == "cleanup":
        manager.cleanup()


if __name__ == "__main__":
    main()
