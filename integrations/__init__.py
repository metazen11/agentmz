"""External task integration module.

Provides provider-agnostic architecture for importing tasks from
external systems like Asana, Jira, Linear, and GitHub Issues.
"""

from integrations.encryption import encrypt_token, decrypt_token
from integrations.providers import get_provider, PROVIDER_REGISTRY

__all__ = [
    "encrypt_token",
    "decrypt_token",
    "get_provider",
    "PROVIDER_REGISTRY",
]
