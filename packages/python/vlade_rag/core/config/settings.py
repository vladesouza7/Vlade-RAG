"""Process configuration.

Values come from environment variables with the ``VLADE_`` prefix. Nested fields use ``__`` as
separator, for example ``VLADE_API__PORT=8000``. See docs/ARCHITECTURE.md section 9.1.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "staging", "prod"]


class ApiSettings(BaseModel):
    """HTTP server settings."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class Settings(BaseSettings):
    """Root settings object."""

    model_config = SettingsConfigDict(
        env_prefix="VLADE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api: ApiSettings = Field(default_factory=ApiSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings, loaded once."""
    return Settings()
