"""Loading of evaluation datasets (JSON Lines)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vlade_rag.core.domain import InvalidArgument
from vlade_rag.evaluation.datasets import load_dataset, parse_dataset

ROOT = Path(__file__).parents[2]


def test_a_valid_dataset() -> None:
    items = parse_dataset(
        '{"question": " Qual o prazo? ", "relevant_documents": ["a.md", "b.md", "a.md"],'
        ' "expected_answer": "Sete dias.", "law": "x"}\n\n'
        '{"question": "Outra?", "relevant_documents": ["c.md"]}\n'
    )
    assert [i.question for i in items] == ["Qual o prazo?", "Outra?"]
    assert items[0].relevant_document_titles == ("a.md", "b.md")  # no repetition, same order
    assert items[0].expected_answer == "Sete dias." and items[1].expected_answer is None


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("not json", "invalid JSON"),
        ("[1, 2]", "JSON object"),
        ('{"relevant_documents": ["a.md"]}', "'question'"),
        ('{"question": "  ", "relevant_documents": ["a.md"]}', "'question'"),
        ('{"question": "q"}', "'relevant_documents'"),
        ('{"question": "q", "relevant_documents": []}', "'relevant_documents'"),
        ('{"question": "q", "relevant_documents": [1]}', "'relevant_documents'"),
        ('{"question": "q", "relevant_documents": "a.md"}', "'relevant_documents'"),
    ],
)
def test_invalid_lines_say_where_the_problem_is(line: str, message: str) -> None:
    with pytest.raises(InvalidArgument, match=message) as caught:
        parse_dataset(
            f'{{"question": "ok", "relevant_documents": ["a"]}}\n{line}', source="d.jsonl"
        )
    assert "d.jsonl:2" in str(caught.value)


def test_an_empty_dataset_is_refused() -> None:
    with pytest.raises(InvalidArgument, match="no question"):
        parse_dataset("\n\n")


def test_a_missing_file_is_refused() -> None:
    with pytest.raises(InvalidArgument, match="Cannot read"):
        load_dataset(ROOT / "nope.jsonl")


def test_the_legal_dataset_of_the_repository_loads() -> None:
    items = load_dataset(ROOT / "evals" / "datasets" / "legal-ptbr" / "questions.jsonl")
    assert len(items) == 20
    assert all(i.relevant_document_titles and i.expected_answer for i in items)
    docs = {p.name for p in (ROOT / "evals" / "datasets" / "legal-ptbr" / "docs").glob("*.md")}
    assert all(set(i.relevant_document_titles) <= docs for i in items)  # every title exists
