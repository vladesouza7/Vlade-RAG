import pytest
from pydantic import ValidationError

from vlade_rag.core.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.environment == "dev"
    assert settings.api.host == "127.0.0.1"
    assert settings.api.port == 8000


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_ENVIRONMENT", "staging")
    monkeypatch.setenv("VLADE_API__HOST", "0.0.0.0")  # noqa: S104 - test value
    monkeypatch.setenv("VLADE_API__PORT", "9000")
    settings = Settings()
    assert settings.environment == "staging"
    assert settings.api.host == "0.0.0.0"  # noqa: S104 - test value
    assert settings.api.port == 9000


def test_invalid_port_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_API__PORT", "70000")
    with pytest.raises(ValidationError):
        Settings()


def test_semantic_cache_is_off_by_default() -> None:
    semantic = Settings().cache.semantic
    assert semantic.enabled is False
    assert semantic.threshold == 0.98


def test_semantic_cache_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_CACHE__SEMANTIC__ENABLED", "true")
    monkeypatch.setenv("VLADE_CACHE__SEMANTIC__THRESHOLD", "0.75")
    monkeypatch.setenv("VLADE_CACHE__SEMANTIC__MAX_ENTRIES", "16")
    settings = Settings()
    assert settings.cache.semantic.enabled is True
    assert settings.cache.semantic.threshold == 0.75
    assert settings.cache.semantic.max_entries == 16


def test_source_connectors_are_off_by_default() -> None:
    sources = Settings().sources
    assert sources.web.seeds == []
    assert sources.google_drive.access_token is None
    assert sources.sql.url is None


def test_source_connector_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_SOURCES__WEB__SEEDS", '["https://docs.example.com"]')
    monkeypatch.setenv("VLADE_SOURCES__GOOGLE_DRIVE__ACCESS_TOKEN", "token")
    monkeypatch.setenv("VLADE_SOURCES__SQL__URL", "sqlite+aiosqlite:///tmp/source.db")
    monkeypatch.setenv("VLADE_SOURCES__SQL__QUERY", "SELECT title FROM documents")
    settings = Settings()
    assert settings.sources.web.seeds == ["https://docs.example.com"]
    token = settings.sources.google_drive.access_token
    assert token is not None and token.get_secret_value() == "token"
    assert settings.sources.sql.query == "SELECT title FROM documents"


def test_vector_index_backend_defaults_to_pgvector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VLADE_VECTOR_INDEX__BACKEND", raising=False)
    assert Settings().vector_index.backend == "postgres"


def test_qdrant_backend_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_VECTOR_INDEX__BACKEND", "qdrant")
    monkeypatch.setenv("VLADE_VECTOR_INDEX__QDRANT__URL", "http://qdrant:6333")
    monkeypatch.setenv("VLADE_VECTOR_INDEX__QDRANT__API_KEY", "secret")
    settings = Settings()
    assert settings.vector_index.backend == "qdrant"
    assert settings.vector_index.qdrant.url == "http://qdrant:6333"
    key = settings.vector_index.qdrant.api_key
    assert key is not None and key.get_secret_value() == "secret"


def test_empty_provider_keys_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_PROVIDERS__OPENAI__API_KEY", "")
    monkeypatch.setenv("VLADE_PROVIDERS__OPENROUTER__API_KEY", "sk-or")
    settings = Settings()
    assert settings.providers.openai.api_key is None
    assert settings.providers.openai.base_url == "https://api.openai.com/v1"
    assert settings.providers.openrouter.base_url == "https://openrouter.ai/api/v1"
    key = settings.providers.openrouter.api_key
    assert key is not None and key.get_secret_value() == "sk-or"
