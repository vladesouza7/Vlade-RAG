"""Integrity of the ``legal-ptbr-v2`` evaluation dataset and of its summary script. No network."""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest

from vlade_rag.evaluation.datasets import load_dataset

ROOT = Path(__file__).parents[2]
DATASET = ROOT / "evals" / "datasets" / "legal-ptbr-v2"
V1 = ROOT / "evals" / "datasets" / "legal-ptbr"


def rows(name: str) -> list[dict]:
    lines = (DATASET / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / "datasets" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_loader_reads_both_question_files() -> None:
    plain = load_dataset(DATASET / "questions.jsonl")
    typos = load_dataset(DATASET / "questions-typos.jsonl")
    assert len(plain) == len(typos) == 109
    assert all(item.expected_answer for item in plain)


def test_every_relevant_document_exists_and_names_a_law_of_the_dataset() -> None:
    documents = {p.name for p in (DATASET / "docs").glob("*.md")}
    assert len(documents) == 150
    assert {name.split("-")[0] for name in documents} == {"lgpd", "cdc", "mci", "lai"}
    for row in rows("questions.jsonl"):
        assert row["relevant_documents"], row["question"]
        assert set(row["relevant_documents"]) <= documents, row["question"]


def test_the_questions_are_unique_and_v1_comes_first_and_unchanged() -> None:
    questions = rows("questions.jsonl")
    assert len({q["question"] for q in questions}) == len(questions)
    v1 = [json.loads(line) for line in (V1 / "questions.jsonl").read_text("utf-8").splitlines()]
    assert [q["question"] for q in questions[:20]] == [q["question"] for q in v1]
    assert [q["group"] for q in questions[:20]] == ["v1"] * 20
    # The v2 labels may add a relevant document, never drop one of v1.
    for old, new in zip(v1, questions[:20], strict=True):
        assert set(old["relevant_documents"]) <= set(new["relevant_documents"])


def test_the_groups_and_styles() -> None:
    questions = rows("questions.jsonl")
    groups = Counter(q["group"] for q in questions)
    assert groups == {
        "v1": 20,
        "lgpd": 15,
        "cdc": 15,
        "mci": 19,
        "lai": 20,
        "multi": 10,
        "cross": 10,
    }
    assert {q["style"] for q in questions} == {"formal", "colloquial"}
    # A "multi" question needs two documents, and every other group may have more than one.
    assert all(len(q["relevant_documents"]) >= 2 for q in questions if q["group"] == "multi")


def test_every_question_has_evidence_in_a_document_it_lists() -> None:
    for row in rows("questions.jsonl"):
        assert row["evidence"], row["question"]
        assert {e["document"] for e in row["evidence"]} == set(row["relevant_documents"])


def test_the_typo_file_keeps_the_labels_and_changes_most_questions() -> None:
    plain, typos = rows("questions.jsonl"), rows("questions-typos.jsonl")
    assert [t["relevant_documents"] for t in typos] == [p["relevant_documents"] for p in plain]
    changed = sum(1 for p, t in zip(plain, typos, strict=True) if p["question"] != t["question"])
    assert changed >= 100  # a question without a word of 7 letters stays as it is


def test_the_lgpd_and_cdc_documents_are_the_v1_documents() -> None:
    for path in sorted((V1 / "docs").glob("*.md")):
        assert (DATASET / "docs" / path.name).read_bytes() == path.read_bytes(), path.name


def test_summarize_by_group_computes_recall_and_mrr_per_group() -> None:
    script = load_script("summarize_by_group")
    questions = [
        {"group": "a", "style": "formal"},
        {"group": "a", "style": "colloquial"},
        {"group": "multi", "style": "formal"},
    ]
    report = {
        "details": [
            {
                "question": "q1",
                "relevant_documents": ["x"],
                "retrieved_documents": ["x", "y"],
                "first_relevant_rank": 1,
            },
            {
                "question": "q2",
                "relevant_documents": ["x"],
                "retrieved_documents": ["y", "z", "x"],
                "first_relevant_rank": 3,
            },
            {
                "question": "q3",
                "relevant_documents": ["x", "w"],
                "retrieved_documents": ["x", "y"],
                "first_relevant_rank": 1,
            },
        ]
    }
    summary = script.summarize(questions, report)
    assert summary["a"]["n"] == 2
    assert summary["a"]["mrr"] == pytest.approx((1 + 1 / 3) / 2)
    assert summary["a"]["recall@1"] == pytest.approx(0.5)
    assert summary["a"]["recall@10"] == pytest.approx(1.0)
    assert summary["multi"]["recall@10"] == pytest.approx(0.5)  # one of two documents found
    assert summary["style:formal"]["n"] == 2 and summary["all"]["n"] == 3


def test_summarize_by_group_refuses_a_report_of_another_size() -> None:
    script = load_script("summarize_by_group")
    with pytest.raises(SystemExit):
        script.summarize([{"group": "a", "style": "formal"}], {"details": []})
