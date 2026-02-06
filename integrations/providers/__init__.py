"""Provider registry and factory.

Usage:
    from integrations.providers import get_provider, PROVIDER_REGISTRY

    provider = get_provider("asana", token="your-token")
    projects = provider.list_projects()
"""

from integrations.providers.base import (
    TaskIntegrationProvider,
    ExternalProject,
    ExternalTask,
    ExternalAttachment,
)

# Registry maps provider name -> provider class
PROVIDER_REGISTRY: dict[str, type[TaskIntegrationProvider]] = {}


def register_provider(name: str):
    """Decorator to register a provider class.

    Usage:
        @register_provider("asana")
        class AsanaProvider(TaskIntegrationProvider):
            ...
    """
    def decorator(cls: type[TaskIntegrationProvider]):
        PROVIDER_REGISTRY[name] = cls
        return cls
    return decorator


def get_provider(name: str, token: str) -> TaskIntegrationProvider:
    """Factory function to get a provider instance.

    Args:
        name: Provider name (e.g., "asana", "jira")
        token: Decrypted API token for the provider

    Returns:
        An instance of the appropriate provider

    Raises:
        ValueError: If the provider is not registered
    """
    if name not in PROVIDER_REGISTRY:
        available = ", ".join(PROVIDER_REGISTRY.keys()) or "none"
        raise ValueError(f"Unknown provider: {name}. Available: {available}")

    provider_class = PROVIDER_REGISTRY[name]
    return provider_class(token=token)


# Import providers to trigger registration
# This must be at the end to avoid circular imports
from integrations.providers.asana import AsanaProvider  # noqa: E402, F401

__all__ = [
    "TaskIntegrationProvider",
    "ExternalProject",
    "ExternalTask",
    "ExternalAttachment",
    "PROVIDER_REGISTRY",
    "get_provider",
    "register_provider",
]
