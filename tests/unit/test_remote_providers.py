"""Remote providers resolve from settings: OpenRouter, OpenCode and custom compatible APIs."""

from __future__ import annotations

import pytest

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import InvalidArgument
from vlade_rag.core.domain.kb_config import EmbeddingsConfig, GenerationConfig

pytestmark = pytest.mark.anyio


async def test_remote_providers_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_PROVIDERS__OPENROUTER__API_KEY", "sk-or")
    monkeypatch.setenv("VLADE_PROVIDERS__OPENCODE__API_KEY", "sk-oc")
    monkeypatch.setenv(
        "VLADE_PROVIDERS__COMPATIBLE__GROQ__BASE_URL", "https://api.groq.com/openai/v1"
    )
    monkeypatch.setenv("VLADE_PROVIDERS__COMPATIBLE__GROQ__API_KEY", "sk-groq")
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        cases = {
            "openrouter": ("https://openrouter.ai/api/v1", "sk-or"),
            "opencode": ("https://opencode.ai/zen/v1", "sk-oc"),
            "groq": ("https://api.groq.com/openai/v1", "sk-groq"),
        }
        for name, (url, key) in cases.items():
            llm = runtime.deps.llms(GenerationConfig(provider=name, model="m"))
            client = llm.http.client  # type: ignore[attr-defined]
            assert str(client.base_url).rstrip("/") == url
            assert client.headers["authorization"] == f"Bearer {key}"
        embedder = runtime.deps.embeddings(
            EmbeddingsConfig(
                provider="openrouter", model="openai/text-embedding-3-small", dimension=1536
            )
        )
        assert embedder.provider == "openrouter" and embedder.dimension == 1536
        with pytest.raises(InvalidArgument, match="Unknown llm adapter 'nope'"):
            runtime.deps.llms(GenerationConfig(provider="nope", model="m"))
    finally:
        await runtime.aclose()


async def test_default_kb_config_is_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    from vlade_rag.core.application import CreateKnowledgeBase
    from vlade_rag.core.domain import Role

    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    monkeypatch.setenv(
        "VLADE_DEFAULT_KB_CONFIG",
        '{"embeddings": {"provider": "openrouter", "model": "openai/text-embedding-3-small",'
        ' "dimension": 1536}, "generation": {"provider": "openrouter", "model": "a/b"}}',
    )
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        tenant = await runtime.tenants.create_tenant("t", "T")
        key = await runtime.tenants.issue_api_key(
            tenant.id, principal_name="a", roles=frozenset({Role.ADMIN})
        )
        ctx = await runtime.tenants.authenticate(key.key, interface="library")
        use_case = CreateKnowledgeBase(runtime.deps)
        kb = await use_case.execute(
            ctx, slug="kb", name="KB", config={"generation": {"model": "c/d"}}
        )
        assert kb.config.embeddings.provider == "openrouter"
        assert kb.config.embeddings.dimension == 1536
        assert (kb.config.generation.provider, kb.config.generation.model) == ("openrouter", "c/d")
        with pytest.raises(InvalidArgument, match="Invalid knowledge base configuration"):
            await use_case.execute(
                ctx, slug="bad", name="B", config={"chunking": {"max_tokens": 1}}
            )
    finally:
        await runtime.aclose()
