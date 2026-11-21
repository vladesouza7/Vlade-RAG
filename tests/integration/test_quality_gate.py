"""The quality gate of the CI (RF-73, roadmap 3.9, ADR-0024).

Uses the memory backend and a small dataset written to a temporary folder.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.evaluation import gate

pytestmark = pytest.mark.anyio

DOCS = {
    "garantia.md": "# Garantia\n\nA garantia dos equipamentos é de um ano a partir da compra.",
    "prazos.md": "# Prazos\n\nO prazo de entrega padrão é de cinco dias úteis para todo o país.",
    "pagamento.md": "# Pagamento\n\nAceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
}
QUESTIONS = [
    {"question": "Qual é a garantia dos equipamentos?", "relevant_documents": ["garantia.md"]},
    {"question": "Qual é o prazo de entrega?", "relevant_documents": ["prazos.md"]},
    {"question": "Posso pagar com cartão de crédito?", "relevant_documents": ["pagamento.md"]},
]


def write_dataset(root: Path) -> None:
    docs = root / "ds" / "docs"
    docs.mkdir(parents=True)
    for name, text in DOCS.items():
        (docs / name).write_text(text, encoding="utf-8")
    lines = "\n".join(json.dumps(q, ensure_ascii=False) for q in QUESTIONS)
    (root / "ds" / "questions.jsonl").write_text(lines + "\n", encoding="utf-8")


def config(**overrides: object) -> gate.GateConfig:
    data: dict[str, object] = {
        "max_drop": 0.05,
        "metrics": ["recall@1", "mrr"],
        "knowledge_base": {
            "chunking": {"strategy": "markdown", "max_tokens": 64, "overlap_tokens": 8},
            "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
        },
        "runs": [{"name": "ds.lexical", "dataset": "ds", "retrievers": ["lexical"]}],
    }
    data.update(overrides)
    return gate.GateConfig.model_validate(data)


def memory_settings() -> Settings:
    return Settings(storage={"backend": "memory"}, object_storage={"backend": "memory"})  # type: ignore[arg-type]


# ------------------------------------------------------------------ compare


def test_a_drop_above_the_limit_fails() -> None:
    cfg = config()
    measured = {"ds.lexical": {"recall@1": 0.80, "mrr": 0.90}}
    result = gate.compare(cfg, measured, {"ds.lexical": {"recall@1": 0.86, "mrr": 0.90}})
    assert not result.passed
    failed = [c for c in result.checks if c.failed]
    assert [(c.metric, c.change) for c in failed] == [("recall@1", -0.06)]
    assert "FAIL" in "\n".join(gate.format_result(result, cfg))


def test_a_drop_at_the_limit_and_a_rise_pass() -> None:
    cfg = config()
    measured = {"ds.lexical": {"recall@1": 0.80, "mrr": 0.95}}
    result = gate.compare(cfg, measured, {"ds.lexical": {"recall@1": 0.85, "mrr": 0.90}})
    assert result.passed
    assert gate.format_result(result, cfg)[-1] == "PASSED"


def test_a_metric_without_baseline_fails() -> None:
    cfg = config()
    result = gate.compare(cfg, {"ds.lexical": {"recall@1": 1.0, "mrr": 1.0}}, {})
    assert not result.passed
    assert result.missing_baseline == ("ds.lexical/recall@1", "ds.lexical/mrr")


def test_the_config_refuses_repeated_names_and_unknown_fields() -> None:
    run = {"name": "a", "dataset": "ds"}
    with pytest.raises(ValidationError, match="different name"):
        config(runs=[run, run])
    with pytest.raises(ValidationError):
        config(runs=[{**run, "unknown": 1}])
    with pytest.raises(ValidationError):
        config(runs=[{**run, "retrievers": ["semantic"]}])


def test_the_repository_gate_file_is_valid() -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = gate.load_config(root / "evals/gate/gate.json")
    baseline = gate.load_baseline(root / "evals/gate/baseline.json")
    for run in cfg.runs:
        assert (root / run.dataset / "docs").is_dir()
        assert (root / run.dataset / run.questions).is_file()
        assert set(cfg.metrics) <= set(baseline[run.name])


# ------------------------------------------------------------------ run


async def test_the_gate_measures_the_same_metrics_twice(tmp_path: Path) -> None:
    write_dataset(tmp_path)
    cfg = config()
    results = []
    for _ in range(2):
        runtime = await build_runtime(memory_settings(), load_plugins=False)
        try:
            results.append(await gate.run_gate(runtime, cfg, tmp_path))
        finally:
            await runtime.aclose()
    assert results[0].metrics == results[1].metrics
    assert results[0].metrics["ds.lexical"]["recall@1"] == 1.0


def test_the_cli_fails_on_a_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vlade_rag.cli.app import app

    write_dataset(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    (tmp_path / "gate.json").write_text(config().model_dump_json(), encoding="utf-8")
    args = ["eval", "gate", "--config", "gate.json", "--baseline", "baseline.json"]
    runner = CliRunner()

    created = runner.invoke(app, [*args, "--update-baseline"])
    assert created.exit_code == 0, created.output
    assert runner.invoke(app, args).exit_code == 0

    baseline = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    baseline["runs"]["ds.lexical"]["mrr"] = 1.5  # a baseline no run can reach
    (tmp_path / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    failed = runner.invoke(app, args)
    assert failed.exit_code == 1
    assert "FAILED" in failed.output
