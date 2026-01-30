"""Ollama service management with SSH restart capability.

This service manages the ollama container lifecycle, providing:
- Status checks (container + API health)
- Service restart via SSH (preferred, cloud-ready)
- Container restart via Docker SDK (fallback)

Environment Variables:
    OLLAMA_SSH_HOST: Hostname of ollama container (default: wfhub-v2-ollama)
    OLLAMA_SSH_PORT: SSH port inside ollama container (default: 22)
    SSH_KEY_DIR: Directory containing SSH keys (default: /ssh_keys)
    SSH_KEY_TYPE: Key type - ed25519 or rsa (default: ed25519)
    OLLAMA_SSH_USER: SSH username (default: root)
"""

import asyncio
import os
import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import docker
import docker.errors
import httpx

logger = logging.getLogger(__name__)


class OllamaStatus(str, Enum):
    """Status of ollama service."""
    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    ERROR = "error"
    UNKNOWN = "unknown"


class RestartMethod(str, Enum):
    """Method used to restart ollama."""
    SSH = "ssh"
    DOCKER_EXEC = "docker_exec"
    CONTAINER_RESTART = "container_restart"


@dataclass
class RestartResult:
    """Result of a restart operation."""
    success: bool
    method: str
    message: str
    duration_seconds: float


class OllamaService:
    """Manages ollama service lifecycle."""

    CONTAINER_NAME = "wfhub-v2-ollama"
    OLLAMA_PORT = 11434

    def __init__(self):
        """Initialize service with configuration from environment."""
        self.ssh_host = os.getenv("OLLAMA_SSH_HOST", "wfhub-v2-ollama")
        self.ssh_port = int(os.getenv("OLLAMA_SSH_PORT", "22"))
        self.ssh_user = os.getenv("OLLAMA_SSH_USER", "root")

        # Build SSH key path from directory and type
        key_dir = os.getenv("SSH_KEY_DIR", "/ssh_keys")
        key_type = os.getenv("SSH_KEY_TYPE", "ed25519")
        self.ssh_key_path = os.path.join(key_dir, f"id_{key_type}")

        self._docker_client = None

    @property
    def docker_client(self):
        """Lazy initialization of Docker client."""
        if self._docker_client is None:
            self._docker_client = docker.from_env()
        return self._docker_client

    async def get_status(self) -> dict:
        """Check ollama service status.

        Returns:
            dict with container_status, service_status, models_loaded, error
        """
        result = {
            "container_status": OllamaStatus.UNKNOWN,
            "service_status": OllamaStatus.UNKNOWN,
            "models_loaded": [],
            "error": None,
        }

        # Check container status via Docker
        try:
            container = self.docker_client.containers.get(self.CONTAINER_NAME)
            result["container_status"] = (
                OllamaStatus.RUNNING if container.status == "running"
                else OllamaStatus.STOPPED
            )
        except docker.errors.NotFound:
            result["container_status"] = OllamaStatus.STOPPED
            result["error"] = "Container not found"
            return result
        except Exception as e:
            result["error"] = f"Docker error: {e}"
            return result

        # Check ollama API health
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"http://{self.ssh_host}:{self.OLLAMA_PORT}/api/tags"
                )
                if resp.status_code == 200:
                    result["service_status"] = OllamaStatus.RUNNING
                    data = resp.json()
                    result["models_loaded"] = [
                        m.get("name") for m in data.get("models", [])
                    ]
                else:
                    result["service_status"] = OllamaStatus.ERROR
        except Exception as e:
            result["service_status"] = OllamaStatus.STOPPED
            result["error"] = f"API check failed: {e}"

        return result

    async def restart_via_ssh(self) -> RestartResult:
        """Restart ollama process via SSH.

        Connects to the ollama container via SSH and executes the restart script.
        This is the preferred method as it's cloud-ready (works across machines).

        Returns:
            RestartResult with success status, method used, message, and duration
        """
        start = time.monotonic()

        # Check if key exists
        if not os.path.exists(self.ssh_key_path):
            duration = time.monotonic() - start
            return RestartResult(
                success=False,
                method=RestartMethod.SSH,
                message=f"SSH key not found at {self.ssh_key_path}",
                duration_seconds=duration,
            )

        try:
            import asyncssh

            async with asyncssh.connect(
                self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                client_keys=[self.ssh_key_path],
                known_hosts=None,  # Skip host key verification for internal containers
            ) as conn:
                # Execute the restart script
                result = await conn.run("/opt/restart-ollama.sh", check=False)

                if result.exit_status == 0:
                    duration = time.monotonic() - start
                    return RestartResult(
                        success=True,
                        method=RestartMethod.SSH,
                        message="Ollama restarted successfully via SSH",
                        duration_seconds=duration,
                    )
                else:
                    duration = time.monotonic() - start
                    return RestartResult(
                        success=False,
                        method=RestartMethod.SSH,
                        message=f"Restart script failed: {result.stderr}",
                        duration_seconds=duration,
                    )

        except Exception as e:
            duration = time.monotonic() - start
            logger.error(f"SSH restart failed: {e}")
            return RestartResult(
                success=False,
                method=RestartMethod.SSH,
                message=f"SSH restart failed: {e}",
                duration_seconds=duration,
            )

    async def restart_container(self) -> RestartResult:
        """Full container restart via Docker SDK.

        This is the fallback method when SSH restart fails.
        It's slower but more reliable as it fully restarts the container.

        Returns:
            RestartResult with success status, method used, message, and duration
        """
        start = time.monotonic()

        try:
            container = self.docker_client.containers.get(self.CONTAINER_NAME)

            # Restart with 30 second timeout
            container.restart(timeout=30)

            # Wait for ollama to be ready
            for _ in range(60):
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(
                            f"http://{self.ssh_host}:{self.OLLAMA_PORT}/api/tags"
                        )
                        if resp.status_code == 200:
                            duration = time.monotonic() - start
                            return RestartResult(
                                success=True,
                                method=RestartMethod.CONTAINER_RESTART,
                                message="Container restarted successfully",
                                duration_seconds=duration,
                            )
                except Exception:
                    pass
                await asyncio.sleep(1)

            duration = time.monotonic() - start
            return RestartResult(
                success=False,
                method=RestartMethod.CONTAINER_RESTART,
                message="Container restarted but ollama not responding",
                duration_seconds=duration,
            )

        except docker.errors.NotFound:
            duration = time.monotonic() - start
            return RestartResult(
                success=False,
                method=RestartMethod.CONTAINER_RESTART,
                message="Container not found",
                duration_seconds=duration,
            )
        except Exception as e:
            duration = time.monotonic() - start
            logger.error(f"Container restart failed: {e}")
            return RestartResult(
                success=False,
                method=RestartMethod.CONTAINER_RESTART,
                message=f"Container restart failed: {e}",
                duration_seconds=duration,
            )

    async def restart_with_fallback(self) -> RestartResult:
        """Attempt restart using cascading fallback strategy.

        Order:
        1. SSH restart (preferred, cloud-ready)
        2. Full container restart (fallback, more reliable)

        Returns:
            RestartResult with success status, method used, message, and duration
        """
        # Try SSH first if key exists
        if os.path.exists(self.ssh_key_path):
            result = await self.restart_via_ssh()
            if result.success:
                return result
            logger.warning(f"SSH restart failed: {result.message}, falling back to container restart...")
        else:
            logger.info("SSH key not found, using container restart directly")

        # Fallback to container restart
        return await self.restart_container()


# Singleton instance
_ollama_service: Optional[OllamaService] = None


def get_ollama_service() -> OllamaService:
    """Get or create the OllamaService singleton."""
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService()
    return _ollama_service
