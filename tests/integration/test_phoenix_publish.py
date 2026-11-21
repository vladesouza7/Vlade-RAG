"""Publishing an answer evaluation to Arize Phoenix (ADR-0026).

A fake client checks the requests. ``VLADE_TEST_PHOENIX_URL`` (for example
http://127.0.0.1:6006) runs the same report against a real Phoenix server.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

import pytest

from vlade_rag.core.domain import InvalidArgument
from vlade_rag.evaluation.phoenix import PhoenixClient, publish_report

REPORT: dict[str, Any] = {
    "metrics": {"faithfulness": 1.0, "grounded_rate": 0.5},
    "config": {
        "evaluator": "answers",
        "date": "2026-11-21T12:00:00+00:00",
        "vlade_rag_version": "0.0.0",
        "knowledge_base": {"slug": "legal"},
        "knowledge_base_config": {
            "retrieval": {"retrievers": ["dense", "lexical"], "rerank": {"enabled": False}},
            "generation": {"model": "m"},
        },
        "scorer": {"name": "ragas", "judge_model": "j"},
    },
    "details": [
        {
            "question": "Qual é o prazo?",
            "expected_answer": "Sete dias.",
            "answer": "Sete dias [1].",
            "grounded": True,
            "cited_documents": ["a.md"],
            "context_documents": ["a.md"],
            "scores": {"faithfulness": 1.0, "answer_relevancy": 0.9, "context_recall": None},
            "seconds": 1.5,
        },
        {
            "question": "xyzzy",
            "expected_answer": None,
            "answer": "Não encontrei.",
            "grounded": False,
            "scores": {"faithfulness": None},
            "seconds": 0.2,
        },
    ],
}


class FakePhoenix(PhoenixClient):
    def __init__(self, existing: bool = False) -> None:
        super().__init__("http://phoenix:6006")
        self.requests: list[tuple[str, str, Any]] = []
        self.existing = existing

    def call(self, method: str, path: str, body: Any | None = None) -> Any:
        self.requests.append((method, path, body))
        if path.startswith("/v1/datasets?name="):
            return {"data": [{"id": "ds1"}] if self.existing else []}
        if path.startswith("/v1/datasets/upload"):
            return {"data": {"dataset_id": "ds1"}}
        if path == "/v1/datasets/ds1/examples":
            questions = [d["question"] for d in REPORT["details"]]
            if self.existing:
                questions = questions[:1]
            return {
                "data": {
                    "examples": [
                        {"id": f"ex{i}", "input": {"question": q}} for i, q in enumerate(questions)
                    ]
                }
            }
        if path == "/v1/datasets/ds1/experiments":
            return {"data": {"id": "exp1"}}
        if path == "/v1/experiments/exp1/runs":
            return {"data": {"id": f"run{len(self.requests)}"}}
        return {"data": {"id": "eval"}}


def test_the_report_becomes_a_dataset_an_experiment_runs_and_evaluations() -> None:
    client = FakePhoenix()
    result = publish_report(client, REPORT, dataset_name="legal")
    upload = next(b for m, p, b in client.requests if p.startswith("/v1/datasets/upload"))
    assert upload["inputs"] == [{"question": "Qual é o prazo?"}, {"question": "xyzzy"}]
    assert upload["outputs"][0] == {"expected_answer": "Sete dias."}
    experiment = next(b for m, p, b in client.requests if p.endswith("/experiments"))
    assert experiment["name"].startswith("legal dense+lexical no-rerank")
    assert experiment["metadata"]["scorer"]["judge_model"] == "j"
    runs = [b for m, p, b in client.requests if p.endswith("/runs")]
    assert [r["dataset_example_id"] for r in runs] == ["ex0", "ex1"]
    assert runs[0]["output"]["answer"] == "Sete dias [1]."
    assert runs[0]["end_time"] == "2026-11-21T12:00:01.500000+00:00"
    evaluations = [b for m, p, b in client.requests if p == "/v1/experiment_evaluations"]
    names = [(e["name"], e["annotator_kind"], e["result"]["score"]) for e in evaluations]
    # None scores are left out; grounded is a code metric of every run.
    assert names == [
        ("faithfulness", "LLM", 1.0),
        ("answer_relevancy", "LLM", 0.9),
        ("grounded", "CODE", 1.0),
        ("grounded", "CODE", 0.0),
    ]
    assert (result.runs, result.evaluations, result.skipped_questions) == (2, 4, ())
    assert result.url.endswith("/datasets/ds1/compare?experimentId=exp1")


def test_an_existing_dataset_is_reused_and_unknown_questions_are_skipped() -> None:
    client = FakePhoenix(existing=True)
    result = publish_report(client, REPORT, dataset_name="legal", experiment_name="fase 3")
    assert not any(p.startswith("/v1/datasets/upload") for _, p, _ in client.requests)
    assert result.skipped_questions == ("xyzzy",)
    experiment = next(b for m, p, b in client.requests if p.endswith("/experiments"))
    assert experiment["name"] == "fase 3"


def test_a_file_that_is_not_an_answer_report_is_refused() -> None:
    with pytest.raises(InvalidArgument):
        publish_report(FakePhoenix(), {"config": {"evaluator": "retrieval"}}, dataset_name="x")


@pytest.mark.integration
def test_publish_to_a_real_phoenix() -> None:
    url = os.environ.get("VLADE_TEST_PHOENIX_URL")
    if not url:
        pytest.skip("VLADE_TEST_PHOENIX_URL is not set")
    client = PhoenixClient(url)
    name = f"vlade-test-{secrets.token_hex(4)}"
    result = publish_report(client, REPORT, dataset_name=name)
    assert (result.runs, result.evaluations) == (2, 4)
    runs = client.call("GET", f"/v1/experiments/{result.experiment_id}/runs")["data"]
    assert len(runs) == 2
    client.call("DELETE", f"/v1/datasets/{result.dataset_id}")
