"""Phase 1 acceptance report: ask the 20 questions of ``legal-ptbr`` through the REST API.

For each question the report shows the answer, the citations, whether the relevant document is
cited, and whether it appears in the top 5 of ``search``. A person reviews the report
(ROADMAP, phase 1 acceptance criteria).

Usage:
    VLADE_API_URL=http://127.0.0.1:8000 VLADE_API_KEY=vrag_... \\
    python3 scripts/acceptance/phase1_report.py legal evals/reports/phase1-acceptance.md
Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "evals" / "datasets" / "legal-ptbr" / "questions.jsonl"


def post(base: str, key: str, path: str, body: dict[str, Any]) -> Any:
    request = urllib.request.Request(  # noqa: S310 - local API URL from VLADE_API_URL
        f"{base}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310 - local API URL
        return json.loads(response.read())


def main(kb: str, out: Path) -> None:
    base = os.environ.get("VLADE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    key = os.environ["VLADE_API_KEY"]
    items = [json.loads(line) for line in QUESTIONS.read_text("utf-8").splitlines() if line]
    rows = []
    cited_hits = search_hits = grounded = 0
    for n, item in enumerate(items, start=1):
        relevant = set(item["relevant_documents"])
        found = post(
            base, key, f"/v1/knowledge-bases/{kb}/search", {"query": item["question"], "top_k": 5}
        )
        top5 = [r["document_title"] for r in found["results"]]
        started = time.perf_counter()
        answer = post(base, key, f"/v1/knowledge-bases/{kb}/query", {"question": item["question"]})
        seconds = time.perf_counter() - started
        cited = [c["document_title"] for c in answer["citations"]]
        in_top5 = bool(relevant & set(top5))
        in_cited = bool(relevant & set(cited))
        search_hits += in_top5
        cited_hits += in_cited
        grounded += answer["grounded"]
        rows.append((n, item, answer, cited, top5, in_top5, in_cited, seconds))
        print(
            f"{n:2d} top5={in_top5!s:5} cited={in_cited!s:5} grounded={answer['grounded']!s:5} "
            f"{seconds:5.1f}s",
            flush=True,
        )

    total = len(items)
    model = rows[0][2]["model"] if rows else "?"
    lines = [
        "# Relatório de aceite da fase 1",
        "",
        f"- Base: `{kb}`. Dataset: `legal-ptbr` ({total} perguntas).",
        f"- Modelo de geração: `{model}`. Prompt: `{rows[0][2]['prompt_name']}` "
        f"versão {rows[0][2]['prompt_version']}."
        if rows
        else "",
        f"- Documento relevante no top 5 da busca: {search_hits} de {total}.",
        f"- Documento relevante entre as citações da resposta: {cited_hits} de {total}.",
        f"- Respostas com `grounded = true`: {grounded} de {total}.",
        "",
        "Confira cada resposta: a resposta concorda com a resposta esperada? "
        "Cada citação aponta para um trecho que contém a informação citada?",
        "",
    ]
    for n, item, answer, cited, top5, in_top5, in_cited, seconds in rows:
        lines += [
            f"## {n}. {item['question']}",
            "",
            f"- Esperado: {item['expected_answer']}",
            f"- Documento relevante: `{item['relevant_documents'][0]}` "
            f"({item['law'].upper()}, art. {item['article']})",
            f"- Top 5 da busca: {', '.join(f'`{t}`' for t in top5)} "
            f"({'contém' if in_top5 else 'não contém'} o relevante)",
            f"- Citações: {', '.join(f'`{c}`' for c in cited) or 'nenhuma'} "
            f"({'contém' if in_cited else 'não contém'} o relevante)",
            f"- Grounded: {answer['grounded']}. Tempo: {seconds:.1f} s.",
            "",
            "Resposta:",
            "",
            *[f"> {line}" if line else ">" for line in answer["answer"].splitlines()],
            "",
        ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", "utf-8")
    print(f"\nTop5 {search_hits}/{total}, cited {cited_hits}/{total}, grounded {grounded}/{total}")
    print(f"Report: {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], Path(sys.argv[2]))
