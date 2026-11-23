"""Static checks for the five dashboards and the alert rules of task 4.6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS = ROOT / "deploy" / "observability" / "grafana" / "dashboards"
RULES = ROOT / "deploy" / "observability" / "prometheus" / "rules" / "alerts.yml"
PROVOKED = ROOT / "tests" / "promtool" / "alerts.test.yml"

EXPECTED = (
    ("rag-performance", "RAG Performance"),
    ("llm-observability", "LLM Observability"),
    ("retrieval-analytics", "Retrieval Analytics"),
    ("infrastructure", "Infrastructure"),
    ("workflow-monitoring", "Workflow Monitoring"),
)


@pytest.fixture(scope="module")
def alerts() -> dict[str, Any]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_the_five_dashboards_exist() -> None:
    files = {path.stem for path in DASHBOARDS.glob("*.json")}
    assert files == {uid for uid, _ in EXPECTED}


@pytest.mark.parametrize(("uid", "title"), EXPECTED)
def test_dashboard_has_panels_and_datasources(uid: str, title: str) -> None:
    data = json.loads((DASHBOARDS / f"{uid}.json").read_text(encoding="utf-8"))
    assert data["uid"] == uid
    assert data["title"] == title
    assert len(data["panels"]) >= 5
    assert len({panel["id"] for panel in data["panels"]}) == len(data["panels"])
    uids = {target["datasource"]["uid"] for panel in data["panels"] for target in panel["targets"]}
    assert "prometheus" in uids
    assert uids <= {"prometheus", "loki", "tempo"}


def test_dashboard_queries_use_the_metric_catalogue() -> None:
    expressions = " ".join(
        target["expr"]
        for path in DASHBOARDS.glob("*.json")
        for panel in json.loads(path.read_text(encoding="utf-8"))["panels"]
        for target in panel["targets"]
        if target["datasource"]["uid"] == "prometheus"
    )
    for metric in (
        "vlade_requests_total",
        "vlade_request_duration_seconds",
        "vlade_stage_duration_seconds",
        "vlade_llm_tokens_total",
        "vlade_llm_cost_usd_total",
        "vlade_ingestion_jobs_total",
        "vlade_ingestion_queue_depth",
        "vlade_retrieval_results",
        "vlade_answers_grounded_total",
        "vlade_eval_metric",
    ):
        assert metric in expressions, metric


def test_eight_alerts_are_defined(alerts: dict[str, Any]) -> None:
    rules = [rule for group in alerts["groups"] for rule in group["rules"]]
    assert len(rules) == 8
    names = {rule["alert"] for rule in rules}
    assert names == {
        "VladeIngestionFailures",
        "VladeRetrievalLatencyHigh",
        "VladeGenerationErrors",
        "VladeProviderUnavailable",
        "VladeQueueGrowing",
        "VladePostgresDown",
        "VladeMemoryHigh",
        "VladeEvalQualityDrop",
    }
    for rule in rules:
        assert rule["labels"]["severity"] in {"warning", "critical"}
        assert rule["annotations"]["summary"]
        assert rule["annotations"]["description"]


def test_each_alert_has_a_provoked_failure_test(alerts: dict[str, Any]) -> None:
    data = yaml.safe_load(PROVOKED.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    names = {
        probe["alertname"]
        for test in data["tests"]
        for probe in test["alert_rule_test"]
        if probe.get("exp_alerts")
    }
    defined = {rule["alert"] for group in alerts["groups"] for rule in group["rules"]}
    assert names == defined
