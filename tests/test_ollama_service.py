"""Tests for the Ollama restart service.

Run with: pytest tests/test_ollama_service.py -v

These tests use mocking to avoid requiring actual containers running.
For integration tests, use test_ollama_service_integration.py
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Add parent to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestOllamaServiceUnit:
    """Unit tests for OllamaService class with mocked dependencies."""

    @pytest.fixture
    def mock_docker_client(self):
        """Mock Docker client for testing."""
        with patch("docker.from_env") as mock:
            container = MagicMock()
            container.status = "running"
            container.exec_run.return_value = (0, b"Ollama restarted successfully")
            container.restart = MagicMock()
            mock.return_value.containers.get.return_value = container
            yield mock

    @pytest.fixture
    def mock_ssh_success(self):
        """Mock successful SSH connection."""
        with patch("asyncssh.connect") as mock:
            conn = AsyncMock()
            conn.run = AsyncMock(return_value=MagicMock(exit_status=0, stdout="OK"))
            conn.__aenter__ = AsyncMock(return_value=conn)
            conn.__aexit__ = AsyncMock(return_value=None)
            mock.return_value = conn
            yield mock

    @pytest.fixture
    def mock_ssh_failure(self):
        """Mock failed SSH connection."""
        with patch("asyncssh.connect") as mock:
            mock.side_effect = Exception("Connection refused")
            yield mock

    @pytest.fixture
    def mock_httpx_healthy(self):
        """Mock healthy ollama API response."""
        with patch("httpx.AsyncClient") as mock:
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"models": [{"name": "qwen3:1.7b"}]}

            async_client = AsyncMock()
            async_client.get = AsyncMock(return_value=response)
            async_client.__aenter__ = AsyncMock(return_value=async_client)
            async_client.__aexit__ = AsyncMock(return_value=None)
            mock.return_value = async_client
            yield mock

    @pytest.fixture
    def mock_httpx_unhealthy(self):
        """Mock unhealthy ollama API response."""
        with patch("httpx.AsyncClient") as mock:
            async_client = AsyncMock()
            async_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            async_client.__aenter__ = AsyncMock(return_value=async_client)
            async_client.__aexit__ = AsyncMock(return_value=None)
            mock.return_value = async_client
            yield mock

    def test_service_init_reads_env_vars(self):
        """OllamaService should read configuration from environment."""
        from services.ollama_service import OllamaService

        with patch.dict(os.environ, {
            "OLLAMA_SSH_HOST": "custom-host",
            "OLLAMA_SSH_PORT": "2222",
            "SSH_KEY_DIR": "/custom/keys",
            "SSH_KEY_TYPE": "rsa",
        }):
            service = OllamaService()
            assert service.ssh_host == "custom-host"
            assert service.ssh_port == 2222
            assert "rsa" in service.ssh_key_path

    def test_get_status_returns_running(self, mock_docker_client, mock_httpx_healthy):
        """get_status should return running when both container and API healthy."""
        from services.ollama_service import OllamaService, OllamaStatus

        service = OllamaService()
        result = asyncio.run(service.get_status())

        assert result["container_status"] == OllamaStatus.RUNNING
        assert result["service_status"] == OllamaStatus.RUNNING
        assert "qwen3:1.7b" in result["models_loaded"]

    def test_get_status_container_not_found(self, mock_httpx_healthy):
        """get_status should handle missing container."""
        from services.ollama_service import OllamaService, OllamaStatus
        import docker.errors

        with patch("docker.from_env") as mock:
            mock.return_value.containers.get.side_effect = docker.errors.NotFound("Container not found")
            service = OllamaService()
            result = asyncio.run(service.get_status())

            assert result["container_status"] == OllamaStatus.STOPPED
            assert "not found" in result["error"].lower()

    def test_restart_via_ssh_success(self, mock_ssh_success, mock_httpx_healthy):
        """restart_via_ssh should return success on successful SSH command."""
        from services.ollama_service import OllamaService

        with patch.dict(os.environ, {"SSH_KEY_DIR": "/tmp"}):
            with patch("os.path.exists", return_value=True):
                service = OllamaService()
                result = asyncio.run(service.restart_via_ssh())

                assert result.success is True
                assert result.method == "ssh"
                assert result.duration_seconds > 0

    def test_restart_via_ssh_failure(self, mock_ssh_failure):
        """restart_via_ssh should return failure on SSH error."""
        from services.ollama_service import OllamaService

        with patch.dict(os.environ, {"SSH_KEY_DIR": "/tmp"}):
            with patch("os.path.exists", return_value=True):
                service = OllamaService()
                result = asyncio.run(service.restart_via_ssh())

                assert result.success is False
                assert result.method == "ssh"
                assert "Connection refused" in result.message

    def test_restart_container_success(self, mock_docker_client, mock_httpx_healthy):
        """restart_container should return success after container restart."""
        from services.ollama_service import OllamaService

        service = OllamaService()
        result = asyncio.run(service.restart_container())

        assert result.success is True
        assert result.method == "container_restart"
        mock_docker_client.return_value.containers.get.return_value.restart.assert_called_once()

    def test_restart_with_fallback_tries_ssh_first(self, mock_ssh_success, mock_docker_client, mock_httpx_healthy):
        """restart_with_fallback should try SSH first."""
        from services.ollama_service import OllamaService

        with patch.dict(os.environ, {"SSH_KEY_DIR": "/tmp"}):
            with patch("os.path.exists", return_value=True):
                service = OllamaService()
                result = asyncio.run(service.restart_with_fallback())

                assert result.success is True
                assert result.method == "ssh"

    def test_restart_with_fallback_uses_container_when_ssh_fails(
        self, mock_ssh_failure, mock_docker_client, mock_httpx_healthy
    ):
        """restart_with_fallback should fall back to container restart."""
        from services.ollama_service import OllamaService

        with patch.dict(os.environ, {"SSH_KEY_DIR": "/tmp"}):
            with patch("os.path.exists", return_value=True):
                service = OllamaService()
                result = asyncio.run(service.restart_with_fallback())

                assert result.success is True
                assert result.method == "container_restart"


class TestOllamaRouterUnit:
    """Unit tests for ollama router endpoints.

    These tests create a minimal FastAPI app with just the ollama router
    to avoid database dependencies.
    """

    @pytest.fixture
    def mock_service(self):
        """Mock the OllamaService singleton."""
        from services.ollama_service import OllamaStatus, RestartResult

        service = MagicMock()
        service.get_status = AsyncMock(return_value={
            "container_status": OllamaStatus.RUNNING,
            "service_status": OllamaStatus.RUNNING,
            "models_loaded": ["qwen3:1.7b"],
            "error": None,
        })
        service.restart_with_fallback = AsyncMock(return_value=RestartResult(
            success=True,
            method="ssh",
            message="Ollama restarted successfully via SSH",
            duration_seconds=2.5,
        ))
        service.restart_via_ssh = AsyncMock(return_value=RestartResult(
            success=True,
            method="ssh",
            message="Ollama restarted via SSH",
            duration_seconds=1.5,
        ))
        service.restart_container = AsyncMock(return_value=RestartResult(
            success=True,
            method="container_restart",
            message="Container restarted",
            duration_seconds=30.0,
        ))
        return service

    @pytest.fixture
    def client(self, mock_service):
        """Create test client for isolated FastAPI app with ollama router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers import ollama

        # Patch the service before importing router
        with patch("routers.ollama.get_ollama_service", return_value=mock_service):
            # Create minimal app with just ollama router
            app = FastAPI()
            app.include_router(ollama.router)
            yield TestClient(app)

    def test_get_status_endpoint(self, client, mock_service):
        """GET /ollama/status should return service status."""
        response = client.get("/ollama/status")
        assert response.status_code == 200

        data = response.json()
        assert data["container_status"] == "running"
        assert data["service_status"] == "running"

    def test_restart_endpoint(self, client, mock_service):
        """POST /ollama/restart should trigger restart with fallback."""
        response = client.post("/ollama/restart")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["method"] == "ssh"

    def test_restart_ssh_endpoint(self, client, mock_service):
        """POST /ollama/restart/ssh should force SSH restart."""
        response = client.post("/ollama/restart/ssh")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["method"] == "ssh"

    def test_restart_container_endpoint(self, client, mock_service):
        """POST /ollama/restart/container should force container restart."""
        response = client.post("/ollama/restart/container")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["method"] == "container_restart"
