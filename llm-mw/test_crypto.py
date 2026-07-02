"""
Unit tests for the cryptography utilities in utils/crypto.py.
"""

import sys
import os

# Adjust path to import from utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.crypto import encrypt, decrypt


def test_encryption_decryption():
    test_strings = [
        "hello-world",
        "secret_token_12345!@#$%",
        "A" * 1000,  # Long string
        "",  # Empty string
    ]

    for original in test_strings:
        cipher = encrypt(original)
        if original:
            assert cipher != original
            assert len(cipher) > 0
        else:
            assert cipher == ""

        decrypted = decrypt(cipher)
        assert decrypted == original


def test_invalid_decryption():
    try:
        decrypt("invalid_cipher_text")
        assert False, "Should raise ValueError on invalid cipher text"
    except ValueError:
        pass  # Expected


if __name__ == "__main__":
    print("Running crypto tests...")
    test_encryption_decryption()
    test_invalid_decryption()
    print("OK: Crypto tests passed successfully!")
