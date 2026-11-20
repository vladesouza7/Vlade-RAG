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


def test_cli_quota_keys_and_audit(cli: Any, tmp_path: Path) -> None:
    slug = f"acme-{secrets.token_hex(3)}"
    cli("tenant", "create", slug)
    admin = _key(cli, slug, "admin")
    assert "documents=unlimited bytes=unlimited" in cli("tenant", "quota", slug).stdout
    assert "Updated: documents=1" in cli("tenant", "quota", slug, "--documents", "1").stdout
    # Only the given limit changes.
    assert "documents=1 bytes=5000" in cli("tenant", "quota", slug, "--bytes", "5000").stdout

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
    (tmp_path / "a.md").write_text("# A\n\num")
    (tmp_path / "b.md").write_text("# B\n\ndois")
    cli("ingest", "docs", str(tmp_path / "a.md"), "--wait", key=admin)
    assert "Skipped" in cli("ingest", "docs", str(tmp_path / "b.md"), key=admin).output
    usage = json.loads(cli("usage", "--json", key=admin).stdout)
    assert usage["documents"] == 1 and usage["quotas"] == {
        "documents": 1,
        "bytes": 5000,
        "requests_per_day": None,
    }

    audit = json.loads(cli("audit", "list", "--json", key=admin).stdout)
    pairs = {(e["action"], e["outcome"]) for e in audit}
    assert ("document.ingest", "denied") in pairs
    assert ("tenant.quota_update", "success") in pairs
    assert ("api_key.issue", "success") in pairs

    prefix = cli("key", "list", "--tenant", slug).stdout.split("\t")[0]
    cli("key", "revoke", prefix, "--tenant", slug)
    assert "revoked" in cli("key", "list", "--tenant", slug).stdout
    cli("tenant", "quota", slug, "--clear")
    assert "documents=unlimited bytes=unlimited" in cli("tenant", "quota", slug).stdout


def test_cli_requests_per_day_quota(cli: Any) -> None:
    slug = f"acme-{secrets.token_hex(3)}"
    cli("tenant", "create", slug)
    admin = _key(cli, slug, "admin")
    out = cli("tenant", "quota", slug, "--requests-per-day", "1000").stdout
    assert "requests_per_day=1000" in out and "documents=unlimited" in out
    usage = json.loads(cli("usage", "--json", key=admin).stdout)
    assert usage["quotas"]["requests_per_day"] == 1000 and usage["requests_today"] == 0
    assert "requests today: 0 / 1000" in cli("usage", key=admin).stdout


def test_cli_eval_run(cli: Any, tmp_path: Path) -> None:
    slug = f"acme-{secrets.token_hex(3)}"
    cli("tenant", "create", slug)
    admin, reader = _key(cli, slug, "admin"), _key(cli, slug, "reader")
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
    (folder / "ferias.md").write_text(
        "# Férias\n\nO funcionário tem trinta dias de férias por ano."
    )
    (folder / "refeicao.md").write_text("# Vale\n\nO vale-refeição é pago no quinto dia útil.")
    cli("ingest", "docs", str(folder), "--wait", key=admin)

    dataset = tmp_path / "q.jsonl"
    dataset.write_text(
        '{"question": "dias de férias por ano", "relevant_documents": ["ferias.md"]}\n'
        '{"question": "vale-refeição quinto dia útil", "relevant_documents": ["refeicao.md"]}\n'
    )
    report_file = tmp_path / "report.json"
    out = cli(
        "eval",
        "run",
        "docs",
        "--dataset",
        str(dataset),
        "--k",
        "5",
        "--output",
        str(report_file),
        key=admin,
    ).stdout
    assert "2 questions" in out and "recall@5" in out and "mrr" in out
    saved = json.loads(report_file.read_text())
    assert saved["metrics"]["mrr"] == 1.0 and saved["items"] == 2
    assert saved["config"]["knowledge_base"]["slug"] == "docs"

    printed = json.loads(
        cli("eval", "run", "docs", "--dataset", str(dataset), "--json", key=admin).stdout
    )
    assert printed["metrics"]["recall@10"] == 1.0

    bad = CliRunner().invoke(
        app, ["eval", "run", "docs", "--dataset", str(dataset)], env={"VLADE_API_KEY": reader}
    )
    assert bad.exit_code == 2 and "forbidden" in bad.output
