"""Tests for external task integration system.

Tests cover:
- Token encryption/decryption
- Integration API endpoints
- Provider interface (with mocked responses)
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set encryption key before importing modules
os.environ["INTEGRATION_ENCRYPTION_KEY"] = "test-key-32-bytes-long-for-fernet!"

# Ensure we use the test database
os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL",
    "postgresql://wfhub:wfhub@localhost:5433/agentic",
)


class TestEncryption:
    """Tests for token encryption module."""

    def test_encrypt_token_returns_string(self):
        """Encrypted token should be a base64 string."""
        # Generate a proper Fernet key for testing
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        os.environ["INTEGRATION_ENCRYPTION_KEY"] = key

        # Reimport to pick up the new key
        import importlib
        import integrations.encryption as enc_module
        importlib.reload(enc_module)

        from integrations.encryption import encrypt_token

        token = "my-secret-api-token"
        encrypted = encrypt_token(token)

        assert isinstance(encrypted, str)
        assert encrypted != token
        assert len(encrypted) > 0

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting should return original token."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        os.environ["INTEGRATION_ENCRYPTION_KEY"] = key

        import importlib
        import integrations.encryption as enc_module
        importlib.reload(enc_module)

        from integrations.encryption import encrypt_token, decrypt_token

        token = "my-secret-api-token-12345"
        encrypted = encrypt_token(token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == token

    def test_encrypt_empty_token_raises(self):
        """Encrypting empty token should raise ValueError."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        os.environ["INTEGRATION_ENCRYPTION_KEY"] = key

        import importlib
        import integrations.encryption as enc_module
        importlib.reload(enc_module)

        from integrations.encryption import encrypt_token

        with pytest.raises(ValueError, match="cannot be empty"):
            encrypt_token("")

    def test_is_encryption_configured(self):
        """Should detect when encryption key is set."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        os.environ["INTEGRATION_ENCRYPTION_KEY"] = key

        import importlib
        import integrations.encryption as enc_module
        importlib.reload(enc_module)

        from integrations.encryption import is_encryption_configured

        assert is_encryption_configured() is True


class TestProviderBase:
    """Tests for provider interface."""

    def test_external_task_dataclass(self):
        """ExternalTask should hold task data correctly."""
        from integrations.providers.base import ExternalTask, ExternalAttachment

        task = ExternalTask(
            external_id="123",
            title="Test Task",
            description="Test description",
            completed=False,
            external_url="https://example.com/task/123",
        )

        assert task.external_id == "123"
        assert task.title == "Test Task"
        assert task.completed is False
        assert task.subtasks == []
        assert task.attachments == []

    def test_external_project_dataclass(self):
        """ExternalProject should hold project data correctly."""
        from integrations.providers.base import ExternalProject

        project = ExternalProject(
            external_id="456",
            name="Test Project",
            external_url="https://example.com/project/456",
        )

        assert project.external_id == "456"
        assert project.name == "Test Project"
        assert project.metadata == {}

    def test_provider_registry(self):
        """Asana provider should be registered."""
        from integrations.providers import PROVIDER_REGISTRY

        assert "asana" in PROVIDER_REGISTRY

    def test_get_provider_unknown_raises(self):
        """Getting unknown provider should raise ValueError."""
        from integrations.providers import get_provider

        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent", "token")


class TestAsanaProvider:
    """Tests for Asana provider with mocked API."""

    @patch("httpx.Client")
    def test_validate_credential_success(self, mock_client_class):
        """Valid token should return True."""
        # Mock the HTTP client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"name": "Test User", "gid": "123"}}
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response

        from integrations.providers.asana import AsanaProvider

        provider = AsanaProvider(token="test-token")
        result = provider.validate_credential()

        assert result is True
        mock_client.request.assert_called_once()

    @patch("httpx.Client")
    def test_validate_credential_invalid(self, mock_client_class):
        """Invalid token should return False."""
        import httpx

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client.request.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        )

        from integrations.providers.asana import AsanaProvider

        provider = AsanaProvider(token="invalid-token")
        result = provider.validate_credential()

        assert result is False

    @patch("httpx.Client")
    def test_list_projects(self, mock_client_class):
        """Should return list of ExternalProject objects."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock workspaces response
        workspaces_response = MagicMock()
        workspaces_response.json.return_value = {
            "data": [{"gid": "ws1", "name": "Workspace 1"}],
        }
        workspaces_response.raise_for_status = MagicMock()

        # Mock projects response
        projects_response = MagicMock()
        projects_response.json.return_value = {
            "data": [
                {"gid": "p1", "name": "Project 1", "permalink_url": "https://asana.com/p1"},
                {"gid": "p2", "name": "Project 2", "permalink_url": "https://asana.com/p2"},
            ],
        }
        projects_response.raise_for_status = MagicMock()

        mock_client.request.side_effect = [workspaces_response, projects_response]

        from integrations.providers.asana import AsanaProvider

        provider = AsanaProvider(token="test-token")
        projects = provider.list_projects()

        assert len(projects) == 2
        assert projects[0].external_id == "p1"
        assert projects[0].name == "Project 1"
        assert projects[1].external_id == "p2"

    @patch("httpx.Client")
    def test_list_tasks(self, mock_client_class):
        """Should return list of ExternalTask objects."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"gid": "t1", "name": "Task 1", "notes": "Description 1", "completed": False},
                {"gid": "t2", "name": "Task 2", "notes": "Description 2", "completed": True},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.request.return_value = mock_response

        from integrations.providers.asana import AsanaProvider

        provider = AsanaProvider(token="test-token")
        tasks = provider.list_tasks("project-123")

        assert len(tasks) == 2
        assert tasks[0].external_id == "t1"
        assert tasks[0].title == "Task 1"
        assert tasks[0].completed is False
        assert tasks[1].completed is True


class TestIntegrationModels:
    """Tests for integration database models."""

    def test_integration_provider_to_dict(self):
        """IntegrationProvider.to_dict should return expected fields."""
        from models import IntegrationProvider
        from datetime import datetime

        provider = IntegrationProvider(
            id=1,
            name="asana",
            display_name="Asana",
            auth_type="pat",
            enabled=True,
            created_at=datetime.utcnow(),
        )

        result = provider.to_dict()

        assert result["id"] == 1
        assert result["name"] == "asana"
        assert result["display_name"] == "Asana"
        assert result["auth_type"] == "pat"
        assert result["enabled"] is True

    def test_integration_credential_to_dict_no_token(self):
        """IntegrationCredential.to_dict should NOT include token."""
        from models import IntegrationCredential
        from datetime import datetime

        credential = IntegrationCredential(
            id=1,
            provider_id=1,
            name="My Account",
            encrypted_token="secret-encrypted-value",
            is_valid=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        result = credential.to_dict()

        assert "encrypted_token" not in result
        assert result["name"] == "My Account"
        assert result["is_valid"] is True


class TestIntegrationAPI:
    """Tests for integration API endpoints.

    These tests require the full app to be importable (all dependencies installed).
    Skip if langchain is not available.
    """

    @pytest.fixture
    def client(self):
        """Create test client."""
        pytest.importorskip("langchain", reason="langchain required for API tests")
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_list_providers(self, client):
        """GET /integrations/providers should return providers."""
        response = client.get("/integrations/providers")
        assert response.status_code == 200

        providers = response.json()
        assert isinstance(providers, list)
        # Should have seeded providers
        provider_names = [p["name"] for p in providers]
        assert "asana" in provider_names

    def test_list_credentials_empty(self, client):
        """GET /integrations/credentials should return list."""
        response = client.get("/integrations/credentials")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_credential_missing_provider(self, client):
        """POST /integrations/credentials with invalid provider should fail."""
        response = client.post(
            "/integrations/credentials",
            json={
                "provider_id": 99999,
                "name": "Test",
                "token": "test-token",
            },
        )
        assert response.status_code == 404
        assert "Provider not found" in response.json()["detail"]

    def test_get_credential_not_found(self, client):
        """GET /integrations/credentials/{id} should return 404 for missing."""
        response = client.get("/integrations/credentials/99999")
        assert response.status_code == 404

    def test_delete_credential_not_found(self, client):
        """DELETE /integrations/credentials/{id} should return 404 for missing."""
        response = client.delete("/integrations/credentials/99999")
        assert response.status_code == 404

    def test_list_project_mappings(self, client):
        """GET /integrations/project-mappings should return list."""
        response = client.get("/integrations/project-mappings")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_integration_not_found(self, client):
        """GET /integrations/project-mappings/{id} should return 404 for missing."""
        response = client.get("/integrations/project-mappings/99999")
        assert response.status_code == 404

    def test_import_tasks_missing_integration(self, client):
        """POST /integrations/import with missing integration should fail."""
        response = client.post(
            "/integrations/import",
            json={
                "integration_id": 99999,
                "task_ids": ["t1", "t2"],
            },
        )
        assert response.status_code == 404
        assert "Integration not found" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
