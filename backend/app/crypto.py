"""Symmetric encryption for the secret columns of the endpoint table.

Secrets are never stored in clear and never leave the backend: the API exposes only
`has_<field>` booleans. The key comes from SECRET_KEY and is required at startup.
"""

from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CryptoError(RuntimeError):
    """Raised when the configured key is unusable or a value cannot be decrypted."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise CryptoError(
            "SECRET_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise CryptoError(
            "SECRET_KEY is not a valid Fernet key (expected urlsafe base64, 32 bytes)."
        ) from exc


def check_key() -> None:
    """Validate the key at startup so a bad config fails loudly, not on first write."""
    _fernet()


def encrypt(value: Optional[str]) -> Optional[str]:
    """Encrypt a secret. None and "" both round-trip to None (i.e. "not set")."""
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    """Decrypt a stored secret, or None if unset."""
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError(
            "Stored secret could not be decrypted - SECRET_KEY has probably changed "
            "since it was written. Re-enter the credentials for this endpoint."
        ) from exc
