from unittest.mock import MagicMock

import pytest
from cryptography.fernet import InvalidToken

from app.auth.crypto import decrypt_token, encrypt_token, get_github_token


def test_encryption_roundtrip():
    token = "gho_testToken1234567890abcdef"
    encrypted = encrypt_token(token)
    assert encrypted != token
    assert encrypted.startswith("gAAAA")
    decrypted = decrypt_token(encrypted)
    assert decrypted == token


def test_decrypt_invalid_ciphertext_raises():
    with pytest.raises(InvalidToken):
        decrypt_token("not-a-valid-fernet-token")


def test_get_github_token_from_user():
    token = "gho_secretAccessPayload987654321"
    encrypted = encrypt_token(token)
    mock_user = MagicMock()
    mock_user.encrypted_github_token = encrypted

    assert get_github_token(mock_user) == token
