"""Summarize ``vlade-rag eval run`` reports by question group and by question style.

A report holds one number per metric for the whole dataset. This script reads the per-question
detail of the report and the dataset file (the ``group`` and ``style`` fields of each question) and
prints Recall@1, Recall@10 and MRR for each group, so a technique that helps one kind of question
and hurts another is visible.

Recall@K here is the share of the relevant documents of a question among the first K documents
that the report lists (the report lists 10). The MRR uses the rank of the first relevant document.

Usage: python3 scripts/datasets/summarize_by_group.py DATASET.jsonl REPORT.json [REPORT.json ...]
Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

CUTOFFS = (1, 10)


def load(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def summarize(questions: list[dict], report: dict) -> dict[str, dict[str, float]]:
    details = report["details"]
    if len(details) != len(questions):
        raise SystemExit(
            f"The report has {len(details)} questions and the dataset has {len(questions)}."
        )
    buckets: dict[str, list[dict[str, float]]] = defaultdict(list)
    for question, detail in zip(questions, details, strict=True):
        if detail["question"].strip() == "":
            raise SystemExit("The report has an empty question.")
        relevant = set(detail["relevant_documents"])
        retrieved = detail["retrieved_documents"]
        first = detail["first_relevant_rank"]
        row = {"mrr": 1.0 / first if first else 0.0}
        for k in CUTOFFS:
            row[f"recall@{k}"] = len(relevant & set(retrieved[:k])) / len(relevant)
        for key in (question["group"], f"style:{question['style']}", "all"):
            buckets[key].append(row)
    return {
        key: {
            "n": len(rows),
            **{metric: sum(r[metric] for r in rows) / len(rows) for metric in rows[0]},
        }
        for key, rows in buckets.items()
    }


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    questions = load(sys.argv[1])
    reports = {Path(p).stem: json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:]}
    summaries = {name: summarize(questions, report) for name, report in reports.items()}
    keys = sorted(
        next(iter(summaries.values())), key=lambda k: (k == "all", k.startswith("style"), k)
    )
    print("| report | " + " | ".join(f"{k} (MRR / R@1 / R@10)" for k in keys) + " |")
    print("|---|" + "---|" * len(keys))
    for name, summary in summaries.items():
        cells = [
            "{:.3f} / {:.2f} / {:.2f}".format(
                summary[k]["mrr"], summary[k]["recall@1"], summary[k]["recall@10"]
            )
            for k in keys
        ]
        print(f"| {name} | " + " | ".join(cells) + " |")
    first = next(iter(summaries.values()))
    print("\nquestions:", ", ".join(f"{k}={first[k]['n']:.0f}" for k in keys))


if __name__ == "__main__":
    main()
