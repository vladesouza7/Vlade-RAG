"""Bearer authentication: API keys and optional OIDC/OAuth 2.1 access tokens (task 5.5).

The use cases keep using ``TenantContext``. Both the API and the MCP call
``authenticate_bearer`` with the raw token of the request. An API key follows the existing
``TenantDirectory`` path. A JWT is verified against the configured issuer and JWKS, and its
claims become the tenant and the roles of the context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from vlade_rag.core.config.settings import OidcSettings
from vlade_rag.core.domain import InvalidArgument, Role, TenantContext, Unauthenticated
from vlade_rag.core.ports import TenantDirectory


@dataclass(slots=True)
class OidcVerifier:
    """Verify JWT access tokens and map their claims to a ``TenantContext``."""

    settings: OidcSettings
    tenants: TenantDirectory
    jwks: dict[str, Any] = field(default_factory=dict)
    _client: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.settings.enabled:
            return
        try:
            import jwt  # PyJWT with the crypto extra
        except ImportError as exc:
            raise InvalidArgument(
                'OIDC needs the "oidc" extra: pip install "vlade-rag[oidc]"'
            ) from exc
        if self.jwks and not self.settings.jwks_url:
            return
        if not self.settings.jwks_url:
            raise InvalidArgument("VLADE_AUTH__OIDC__JWKS_URL is required when OIDC is enabled.")
        self._client = jwt.PyJWKClient(self.settings.jwks_url)

    def _signing_key(self, token: str) -> Any:
        import jwt

        if self.jwks:
            header = jwt.get_unverified_header(token)
            key = self.jwks.get(str(header.get("kid", "")))
            if key is None:
                raise Unauthenticated("The token key is not known.")
            if isinstance(key, (str, dict)):
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
            return key
        return self._client.get_signing_key_from_jwt(token).key

    async def verify(self, token: str, *, interface: str) -> TenantContext:
        """Return the tenant context of a valid JWT, or raise ``Unauthenticated``."""
        import jwt

        try:
            payload = jwt.decode(
                token,
                self._signing_key(token),
                algorithms=list(self.settings.algorithms),
                audience=self.settings.audience or None,
                issuer=self.settings.issuer or None,
                options={"require": ["exp"]},
            )
        except jwt.PyJWTError as exc:
            raise Unauthenticated("The access token is not valid.") from exc
        except (ValueError, TypeError, KeyError) as exc:
            raise Unauthenticated("The access token is not valid.") from exc

        tenant_claim = self.settings.tenant_claim
        slug = payload.get(tenant_claim)
        if not isinstance(slug, str) or not slug:
            raise Unauthenticated(f"The access token has no '{tenant_claim}' claim.")
        try:
            tenant = await self.tenants.get_tenant(slug)
        except Exception as exc:  # NotFound and any directory error hide the tenant
            raise Unauthenticated("The access token names an unknown tenant.") from exc

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise Unauthenticated("The access token has no 'sub' claim.")
        principal_id = (
            uuid.UUID(subject)
            if _is_uuid(subject)
            else uuid.uuid5(uuid.NAMESPACE_URL, f"{self.settings.issuer}:{subject}")
        )
        raw_roles = payload.get(self.settings.roles_claim, ("reader",))
        if not isinstance(raw_roles, (list, tuple)):
            raise Unauthenticated(f"The '{self.settings.roles_claim}' claim must be a list.")
        roles = frozenset(
            role for value in raw_roles if (role := _role(value)) is not None
        ) or frozenset({Role.READER})
        return TenantContext(tenant.id, principal_id, roles, interface)  # type: ignore[arg-type]


async def authenticate_bearer(
    tenants: TenantDirectory,
    token: str,
    *,
    interface: str,
    oidc: OidcVerifier | None = None,
) -> TenantContext:
    """Authenticate an API key, then try OIDC when the token looks like a JWT."""
    try:
        return await tenants.authenticate(token, interface=interface)
    except Unauthenticated:
        if oidc is None or not oidc.settings.enabled or not _looks_like_jwt(token):
            raise
        return await oidc.verify(token, interface=interface)


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and all(part for part in token.split("."))


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _role(value: object) -> Role | None:
    if not isinstance(value, str):
        return None
    try:
        return Role(value)
    except ValueError:
        return None


__all__ = ["OidcVerifier", "authenticate_bearer"]
