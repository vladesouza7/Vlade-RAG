"""RSA keys and signed tokens for the OIDC tests (task 5.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "test-key"
ISSUER = "https://idp.example"
AUDIENCE = "vlade"


def signing_keys() -> tuple[Any, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def make_token(
    private: Any,
    *,
    tenant: str = "acme",
    roles: tuple[str, ...] = ("reader",),
    subject: str = "user-1",
    **overrides: Any,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant": tenant,
        "roles": list(roles),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    payload.update(overrides)
    return jwt.encode(payload, private, algorithm="RS256", headers={"kid": KID})
