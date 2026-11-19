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


def test_empty_provider_keys_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLADE_PROVIDERS__OPENAI__API_KEY", "")
    monkeypatch.setenv("VLADE_PROVIDERS__OPENROUTER__API_KEY", "sk-or")
    settings = Settings()
    assert settings.providers.openai.api_key is None
    assert settings.providers.openai.base_url == "https://api.openai.com/v1"
    assert settings.providers.openrouter.base_url == "https://openrouter.ai/api/v1"
    key = settings.providers.openrouter.api_key
    assert key is not None and key.get_secret_value() == "sk-or"
