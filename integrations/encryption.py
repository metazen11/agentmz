"""Token encryption/decryption using Fernet symmetric encryption.

Tokens are encrypted before storage in the database and only decrypted
when making API calls to external providers. The encryption key is stored
in the INTEGRATION_ENCRYPTION_KEY environment variable.
"""

import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Load encryption key from environment
_ENCRYPTION_KEY = os.environ.get("INTEGRATION_ENCRYPTION_KEY")
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Get or initialize the Fernet instance."""
    global _fernet
    if _fernet is None:
        if not _ENCRYPTION_KEY:
            raise ValueError(
                "INTEGRATION_ENCRYPTION_KEY not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token for database storage.

    Args:
        token: The plaintext API token to encrypt

    Returns:
        The encrypted token as a string (base64 encoded)

    Raises:
        ValueError: If INTEGRATION_ENCRYPTION_KEY is not set
    """
    if not token:
        raise ValueError("Token cannot be empty")

    fernet = _get_fernet()
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token from the database.

    Args:
        encrypted_token: The encrypted token (base64 encoded)

    Returns:
        The plaintext API token

    Raises:
        ValueError: If INTEGRATION_ENCRYPTION_KEY is not set
        InvalidToken: If the token is invalid or corrupted
    """
    if not encrypted_token:
        raise ValueError("Encrypted token cannot be empty")

    fernet = _get_fernet()
    try:
        decrypted = fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except InvalidToken as e:
        logger.error("Failed to decrypt token: invalid or corrupted")
        raise


def is_encryption_configured() -> bool:
    """Check if encryption is properly configured.

    Returns:
        True if INTEGRATION_ENCRYPTION_KEY is set, False otherwise
    """
    return bool(_ENCRYPTION_KEY)
