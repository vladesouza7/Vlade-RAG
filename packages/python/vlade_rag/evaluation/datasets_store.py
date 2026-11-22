"""Registry of named evaluation datasets (ADR-0011).

A name is a directory under the server path with a ``questions.jsonl`` file. The caller sends only
the name, never a path. The adapter rejects names that could leave the registry directory.
"""

from __future__ import annotations

import re
from pathlib import Path

from vlade_rag.core.domain import InvalidArgument
from vlade_rag.core.ports import EvalItem
from vlade_rag.evaluation.datasets import load_dataset

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")
QUESTIONS = "questions.jsonl"


class FileEvaluationDatasets:
    def __init__(
        self, root: str | Path, *, max_items: int = 1000, questions: str = QUESTIONS
    ) -> None:
        self.root = Path(root).resolve()
        self.max_items = max_items
        self.questions = questions

    async def list_names(self) -> tuple[str, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(
            sorted(
                path.name
                for path in self.root.iterdir()
                if path.is_dir() and (path / self.questions).is_file()
            )
        )

    async def load(self, name: str) -> tuple[EvalItem, ...]:
        if name in (".", "..") or NAME.fullmatch(name) is None:
            raise InvalidArgument("The dataset name is not valid.")
        path = (self.root / name / self.questions).resolve()
        if self.root not in path.parents:
            raise InvalidArgument("The dataset name is not valid.")
        try:
            items = load_dataset(path)
        except OSError:
            raise InvalidArgument(f"The dataset '{name}' does not exist.") from None
        if len(items) > self.max_items:
            raise InvalidArgument(f"The dataset '{name}' has more than {self.max_items} questions.")
        return tuple(items)
