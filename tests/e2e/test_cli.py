"""CLI end to end against PostgreSQL, including tenant isolation (RNF-07)."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from vlade_rag.cli.app import app
from vlade_rag.core.config import get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def cli(postgres_urls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("VLADE_DATABASE__URL", postgres_urls[1])
    monkeypatch.setenv("VLADE_SECURITY__API_KEY_PEPPER", "test-pepper")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__PATH", str(tmp_path / "objects"))
    get_settings.cache_clear()
    runner = CliRunner()

    def run(*args: str, key: str | None = None) -> Any:
        env = {"VLADE_API_KEY": key} if key else {}
        result = runner.invoke(app, list(args), env=env)
        assert result.exit_code == 0, result.output
        return result

    yield run
    get_settings.cache_clear()


def _key(cli: Any, tenant: str, roles: str) -> str:
    return str(cli("key", "create", "--tenant", tenant, "--roles", roles).stdout.strip())


def test_cli_flow_and_isolation(cli: Any, tmp_path: Path) -> None:
    acme, globex = f"acme-{secrets.token_hex(3)}", f"globex-{secrets.token_hex(3)}"
    cli("tenant", "create", acme)
    cli("tenant", "create", globex)
    admin = _key(cli, acme, "admin")
    other = _key(cli, globex, "admin")
    config = tmp_path / "kb.json"
    config.write_text(
        json.dumps(
            {
                "embeddings": {"provider": "hashing", "model": "h", "dimension": 64},
                "generation": {"provider": "extractive", "model": "extractive"},
            }
        )
    )
    cli("kb", "create", "docs", "--config", str(config), key=admin)
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.md").write_text("# Férias\n\nO funcionário tem trinta dias de férias por ano.")
    (folder / "b.txt").write_text("O vale-refeição é pago no quinto dia útil.")
    out = cli("ingest", "docs", str(folder), "--wait", key=admin).stdout
    assert "Submitted 2 documents" in out

    hits = json.loads(cli("search", "docs", "dias de férias", "--json", key=admin).stdout)
    assert "trinta dias" in hits[0]["text"]
    answer = json.loads(cli("query", "docs", "Quantos dias de férias?", "--json", key=admin).stdout)
    assert answer["grounded"] is True

    assert "docs" not in cli("kb", "list", key=other).stdout
    cli("kb", "create", "docs", "--config", str(config), key=other)
    assert json.loads(cli("search", "docs", "férias", "--json", key=other).stdout) == []
