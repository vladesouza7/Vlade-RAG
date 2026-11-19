"""API key format and hashing (docs/ARCHITECTURE.md section 15).

Format: ``vrag_<prefix>_<secret>``. The prefix is public and indexes the key. The secret has
32 random bytes. Storage keeps only ``HMAC-SHA256(secret, pepper)``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from vlade_rag.core.domain.errors import Unauthenticated

KEY_SCHEME = "vrag"
_PREFIX_BYTES = 6
_SECRET_BYTES = 32


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(key, prefix, secret)``."""
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    return f"{KEY_SCHEME}_{prefix}_{secret}", prefix, secret


def parse_api_key(key: str) -> tuple[str, str]:
    """Return ``(prefix, secret)``. Raise ``Unauthenticated`` for a malformed key."""
    parts = key.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_SCHEME or not parts[1] or not parts[2]:
        raise Unauthenticated("Invalid API key.")
    return parts[1], parts[2]


def hash_secret(secret: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).digest()


def verify_secret(secret: str, pepper: str, expected: bytes) -> bool:
    return hmac.compare_digest(hash_secret(secret, pepper), expected)
