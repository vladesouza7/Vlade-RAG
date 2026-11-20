"""Evaluation datasets in JSON Lines (see ``evals/datasets/README.md``).

Each line is an object with ``question`` and ``relevant_documents`` (the titles of the relevant
documents, which are their file names). ``expected_answer`` is optional. Other fields are kept in
the file and ignored here.
"""

from __future__ import annotations

import json
from pathlib import Path

from vlade_rag.core.domain import InvalidArgument
from vlade_rag.core.ports import EvalItem


def parse_dataset(text: str, *, source: str = "dataset") -> list[EvalItem]:
    items: list[EvalItem] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{source}:{number}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InvalidArgument(f"{where}: invalid JSON ({exc.msg}).") from None
        if not isinstance(row, dict):
            raise InvalidArgument(f"{where}: each line must be a JSON object.")
        question = row.get("question")
        if not isinstance(question, str) or not question.strip():
            raise InvalidArgument(f"{where}: 'question' must be a non-empty text.")
        relevant = row.get("relevant_documents")
        if (
            not isinstance(relevant, list)
            or not relevant
            or not all(isinstance(t, str) and t for t in relevant)
        ):
            raise InvalidArgument(
                f"{where}: 'relevant_documents' must be a list of document titles."
            )
        expected = row.get("expected_answer")
        items.append(
            EvalItem(
                question=question.strip(),
                expected_answer=expected if isinstance(expected, str) else None,
                relevant_document_titles=tuple(dict.fromkeys(relevant)),
            )
        )
    if not items:
        raise InvalidArgument(f"{source}: the dataset has no question.")
    return items


def load_dataset(path: str | Path) -> list[EvalItem]:
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidArgument(f"Cannot read the dataset '{file}': {exc.strerror}.") from None
    return parse_dataset(text, source=file.name)
