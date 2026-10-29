from typing import TYPE_CHECKING

from cryptography.fernet import Fernet

from app.config import get_settings

if TYPE_CHECKING:
    from app.models.user import User


def get_fernet() -> Fernet:
    """Initialize Fernet cipher using configured TOKEN_ENCRYPTION_KEY."""
    settings = get_settings()
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode("utf-8"))


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token using Fernet and return base64 ciphertext."""
    fernet = get_fernet()
    return fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a Fernet ciphertext back to plaintext."""
    fernet = get_fernet()
    return fernet.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")


def get_github_token(user: "User") -> str:
    """Decrypt user's GitHub token on demand.

    This is the only place in BodhCode where token decryption happens.
    Nothing else touches encrypted_github_token directly for reading.
    """
    return decrypt_token(user.encrypted_github_token)


def get_grok_key(user: "User") -> str | None:
    """Decrypt user's Grok API key on demand, if configured."""
    if not user.encrypted_grok_key:
        return None
    return decrypt_token(user.encrypted_grok_key)
