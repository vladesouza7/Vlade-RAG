"""OIDC bearer verification and the shared authentication helper (task 5.5)."""

from __future__ import annotations

import uuid

import pytest

from tests.oidc_helpers import AUDIENCE, ISSUER, KID, make_token, signing_keys
from vlade_rag.auth import OidcVerifier, authenticate_bearer
from vlade_rag.core.config.settings import OidcSettings
from vlade_rag.core.domain import Role, Unauthenticated
from vlade_rag.knowledge.memory import memory_adapters

pytestmark = pytest.mark.anyio


def verifier(public: object) -> OidcVerifier:
    adapters = memory_adapters()
    settings = OidcSettings(
        enabled=True,
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=["RS256"],
    )
    return OidcVerifier(settings, adapters.tenants, jwks={KID: public})


async def test_valid_token_maps_claims_to_a_context() -> None:
    private, public = signing_keys()
    verify = verifier(public)
    tenant = await verify.tenants.create_tenant("acme", "ACME")
    ctx = await verify.verify(make_token(private, roles=("reader", "writer")), interface="api")
    assert ctx.tenant_id == tenant.id
    assert ctx.roles == frozenset({Role.READER, Role.WRITER})
    assert ctx.principal_id == uuid.uuid5(uuid.NAMESPACE_URL, f"{ISSUER}:user-1")
    assert ctx.interface == "api"


async def test_invalid_tokens_are_rejected() -> None:
    private, public = signing_keys()
    verify = verifier(public)
    await verify.tenants.create_tenant("acme", "ACME")
    other_private, _ = signing_keys()
    with pytest.raises(Unauthenticated):
        await verify.verify(make_token(other_private), interface="api")
    with pytest.raises(Unauthenticated):
        await verify.verify(make_token(private, tenant="nope"), interface="api")
    with pytest.raises(Unauthenticated):
        await verify.verify(make_token(private, exp=1), interface="api")
    with pytest.raises(Unauthenticated):
        await verify.verify(make_token(private, tenant=None), interface="api")


async def test_unknown_roles_fall_back_to_reader() -> None:
    private, public = signing_keys()
    verify = verifier(public)
    await verify.tenants.create_tenant("acme", "ACME")
    ctx = await verify.verify(make_token(private, roles=("owner", "admin")), interface="mcp")
    assert ctx.roles == frozenset({Role.ADMIN})


async def test_helper_tries_api_key_then_oidc() -> None:
    private, public = signing_keys()
    adapters = memory_adapters()
    tenant = await adapters.tenants.create_tenant("acme", "ACME")
    issued = await adapters.tenants.issue_api_key(
        tenant.id, principal_name="bot", roles=frozenset({Role.ADMIN})
    )
    settings = OidcSettings(enabled=True, issuer=ISSUER, audience=AUDIENCE)
    oidc = OidcVerifier(settings, adapters.tenants, jwks={KID: public})

    key_ctx = await authenticate_bearer(adapters.tenants, issued.key, interface="api", oidc=oidc)
    assert key_ctx.tenant_id == tenant.id

    token = make_token(private)
    token_ctx = await authenticate_bearer(adapters.tenants, token, interface="api", oidc=oidc)
    assert token_ctx.tenant_id == tenant.id

    with pytest.raises(Unauthenticated):
        await authenticate_bearer(adapters.tenants, token, interface="api", oidc=None)
