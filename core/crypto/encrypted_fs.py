"""Encrypted file blobs (AES-256-GCM, HOLIXENC1 format)."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_MAGIC = b"HOLIXENC1"
NONCE_SIZE = 12


def encrypt_bytes(dek: bytes, plaintext: bytes) -> bytes:
    if len(dek) != 32:
        raise ValueError("DEK must be 32 bytes")
    nonce = _random_nonce()
    aes = AESGCM(dek)
    ciphertext = aes.encrypt(nonce, plaintext, None)
    return ENCRYPTION_MAGIC + nonce + ciphertext


def decrypt_bytes(dek: bytes, payload: bytes) -> bytes:
    if len(payload) < len(ENCRYPTION_MAGIC) + NONCE_SIZE + 16:
        raise ValueError("Encrypted payload too short")
    if not payload.startswith(ENCRYPTION_MAGIC):
        raise ValueError("Not a Holix encrypted file")
    nonce = payload[len(ENCRYPTION_MAGIC) : len(ENCRYPTION_MAGIC) + NONCE_SIZE]
    ciphertext = payload[len(ENCRYPTION_MAGIC) + NONCE_SIZE :]
    aes = AESGCM(dek)
    return aes.decrypt(nonce, ciphertext, None)


def is_encrypted_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(ENCRYPTION_MAGIC))
        return header == ENCRYPTION_MAGIC
    except OSError:
        return False


def read_encrypted_text(path: Path, dek: bytes, *, encoding: str = "utf-8") -> str:
    payload = path.read_bytes()
    return decrypt_bytes(dek, payload).decode(encoding)


def write_encrypted_text(path: Path, dek: bytes, text: str, *, encoding: str = "utf-8") -> int:
    """Write encrypted text; return ciphertext size on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = encrypt_bytes(dek, text.encode(encoding))
    path.write_bytes(payload)
    return len(payload)


def _random_nonce() -> bytes:
    import secrets

    return secrets.token_bytes(NONCE_SIZE)