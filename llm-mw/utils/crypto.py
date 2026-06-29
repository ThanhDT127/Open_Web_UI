"""
Encryption utilities for securely storing OAuth credentials.
Uses AES-256 key derived from MW_SECRET using SHA-256.
"""

import base64
import hashlib
from cryptography.fernet import Fernet
from config import MW_SECRET

# Derive a 32-byte key from MW_SECRET using SHA-256
_key_bytes = hashlib.sha256(MW_SECRET.encode("utf-8")).digest()
_fernet_key = base64.urlsafe_b64encode(_key_bytes)
_fernet = Fernet(_fernet_key)


def encrypt(text: str) -> str:
    """
    Encrypt plaintext into secure ciphertext.
    """
    if not text:
        return ""
    return _fernet.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(cipher_text: str) -> str:
    """
    Decrypt ciphertext back into plaintext.
    Raises ValueError if decryption fails.
    """
    if not cipher_text:
        return ""
    try:
        return _fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}")
