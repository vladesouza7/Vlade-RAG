"""Build the ``legal-ptbr-v2`` evaluation dataset (ROADMAP phase 3, limitation L10).

``legal-ptbr`` (v1) has 20 questions and one relevant document per question. A reranker fills its
metrics, so the dataset cannot rank two retrieval settings. v2 keeps v1 and adds what v1 lacks:

- two more laws with words close to the LGPD and the CDC, so there are hard wrong documents:
  Marco Civil da Internet (Lei 12.965/2014) and Lei de Acesso à Informação (Lei 12.527/2011);
- 90 new questions, in a formal and in a colloquial style, with questions that need two documents
  and questions whose words other laws also use (see ``legal_ptbr_v2_questions``);
- a typo variant of every question (``questions-typos.jsonl``).

Source: original publication of each law, from the Chamber of Deputies site. Texts of laws are not
protected by copyright in Brazil (Lei 9.610/1998, art. 8, IV). The texts are the original
publications, without later amendments. Do not use this dataset as a legal source.

The LGPD and CDC documents are the same as in v1 (same names and same text). The builder checks it.

Usage: python3 scripts/datasets/build_legal_ptbr_v2.py [--cache DIR]
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_legal_ptbr as v1
from derive_legal_ptbr_variants import add_typos
from legal_ptbr_v2_questions import QUESTIONS as NEW_QUESTIONS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "datasets" / "legal-ptbr-v2"
V1_DOCS = ROOT / "evals" / "datasets" / "legal-ptbr" / "docs"

LAWS: dict[str, dict[str, object]] = {
    "lgpd": {**v1.LAWS["lgpd"], "docs": 50},
    "cdc": {**v1.LAWS["cdc"], "docs": 50},
    "mci": {
        "name": "Marco Civil da Internet (Lei 12.965/2014)",
        "url": "https://www2.camara.leg.br/legin/fed/lei/2014/"
        "lei-12965-23-abril-2014-778630-publicacaooriginal-143980-pl.html",
        "docs": 25,
    },
    "lai": {
        "name": "Lei de Acesso à Informação (Lei 12.527/2011)",
        "url": "https://www2.camara.leg.br/legin/fed/lei/2011/"
        "lei-12527-18-novembro-2011-611802-publicacaooriginal-134287-pl.html",
        "docs": 25,
    },
}


def fetch(key: str, cache: Path | None) -> str:
    if cache is not None and (cache / f"{key}.html").exists():
        return (cache / f"{key}.html").read_text("utf-8")
    url = str(LAWS[key]["url"])  # fixed https URLs from LAWS
    request = urllib.request.Request(url, headers={"User-Agent": v1.USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URL
        html = response.read().decode("utf-8")
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{key}.html").write_text(html, "utf-8")
    return html


def build(cache: Path | None) -> None:
    docs_dir = OUT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for old in docs_dir.glob("*.md"):
        old.unlink()

    manifest: dict[str, dict[str, object]] = {}
    article_file: dict[tuple[str, int], str] = {}
    article_text: dict[tuple[str, int], str] = {}
    texts: dict[str, str] = {}
    for key, law in LAWS.items():
        articles = v1.articles_of(v1.lines_of(fetch(key, cache)))
        for number, _, text in articles:
            article_text[(key, number)] = text
        for index, group in enumerate(v1.groups(articles, int(law["docs"])), start=1):  # type: ignore[call-overload]
            first, last = group[0][0], group[-1][0]
            span = f"Art. {first}" if first == last else f"Arts. {first} a {last}"
            name = f"{key}-{index:03d}.md"
            body = [f"# {law['name']} — {span}", ""]
            if group[0][1]:
                body += [f"_{group[0][1]}_", ""]
            body.append("\n\n".join(text for _, _, text in group))
            content = "\n".join(body).strip() + "\n"
            (docs_dir / name).write_text(content, "utf-8")
            texts[name] = content
            manifest[name] = {"law": key, "articles": [n for n, _, _ in group]}
            for number, _, _ in group:
                article_file[(key, number)] = name

    # The LGPD and CDC documents must be the v1 documents, or the v1 questions would change.
    different = [
        name
        for name in sorted(texts)
        if name.startswith(("lgpd-", "cdc-")) and (V1_DOCS / name).read_text("utf-8") != texts[name]
    ]
    if different:
        raise SystemExit(f"The documents differ from legal-ptbr (v1): {different[:5]} ...")

    rows: list[dict[str, object]] = []
    for law, article, question, answer, phrase in v1.QUESTIONS:
        name = article_file[(law, article)]
        if phrase.lower() not in texts[name].lower():
            raise SystemExit(f"Phrase {phrase!r} not found in {name} (v1, Art. {article})")
        rows.append(
            {
                "question": question,
                "expected_answer": answer,
                "relevant_documents": [name],
                "group": "v1",
                "style": "formal",
                "evidence": [{"law": law, "article": article, "document": name}],
            }
        )
    for group, style, question, answer, evidence in NEW_QUESTIONS:
        documents: list[str] = []
        proofs = []
        for law, article, phrase in evidence:
            if (law, article) not in article_file:
                raise SystemExit(f"Article {law} {article} does not exist ({question!r}).")
            if phrase.lower() not in article_text[(law, article)].lower():
                raise SystemExit(f"Phrase {phrase!r} not found in {law} art. {article}.")
            name = article_file[(law, article)]
            if name not in documents:
                documents.append(name)
            proofs.append({"law": law, "article": article, "document": name})
        if group == "multi" and len(documents) < 2:
            raise SystemExit(f"A 'multi' question needs two documents: {question!r}")
        rows.append(
            {
                "question": question,
                "expected_answer": answer,
                "relevant_documents": documents,
                "group": group,
                "style": style,
                "evidence": proofs,
            }
        )
    if len({row["question"] for row in rows}) != len(rows):
        raise SystemExit("Two questions have the same text.")

    def write(name: str, questions: list[str]) -> None:
        with (OUT / name).open("w", encoding="utf-8") as out:
            for row, question in zip(rows, questions, strict=True):
                out.write(json.dumps({**row, "question": question}, ensure_ascii=False) + "\n")

    write("questions.jsonl", [str(row["question"]) for row in rows])
    write("questions-typos.jsonl", [add_typos(str(row["question"])) for row in rows])
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "source": {k: v["url"] for k, v in LAWS.items()},
                "documents": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "utf-8",
    )

    by_group: dict[str, int] = {}
    for row in rows:
        by_group[str(row["group"])] = by_group.get(str(row["group"]), 0) + 1
    multi = sum(1 for row in rows if len(row["relevant_documents"]) > 1)  # type: ignore[arg-type]
    print(f"{len(manifest)} documents, {len(rows)} questions -> {OUT.relative_to(ROOT)}")
    print("questions by group:", dict(sorted(by_group.items())), "| with 2+ documents:", multi)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, help="Folder to cache the downloaded HTML pages.")
    build(parser.parse_args().cache)


if __name__ == "__main__":
    main()
