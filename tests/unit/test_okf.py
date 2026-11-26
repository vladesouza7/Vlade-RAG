"""Unit tests of the OKF v0.2 parser and writer (task 6.10)."""

from __future__ import annotations

from vlade_rag.core.domain import InvalidArgument, RawDocument, WikiPage
from vlade_rag.ingestion.parsers.basic import MarkdownParser
from vlade_rag.okf import parse_page, render_page, validate_bundle
from vlade_rag.okf.parser import split_frontmatter

_PAGE = """---
type: Topic
title: Batismo
description: Estudo sobre o batismo.
tags: [teologia, batismo]
sources:
  - id: joao
    resource: vlade://kb/biblia/documents/123
    title: Joao 3
generated: {by: vlade-rag/wiki-synthesis, at: '2026-11-25T00:00:00Z'}
verified:
  - {by: human:pastor, at: '2026-11-25T12:00:00Z'}
status: stable
stale_after: '2027-11-25T00:00:00Z'
---

# Batismo

O batismo é analisado aqui.[^joao]

[^joao]: Joao 3
"""


def test_split_frontmatter_and_parse_page() -> None:
    frontmatter, body = split_frontmatter(_PAGE)
    assert frontmatter["type"] == "Topic"
    assert body.startswith("# Batismo")

    page = parse_page(_PAGE, "teologia/batismo.md")
    assert page.path == "teologia/batismo.md"
    assert page.type == "Topic"
    assert page.title == "Batismo"
    assert page.tags == ("teologia", "batismo")
    assert page.sources[0].id == "joao"
    assert page.generated is not None
    assert page.generated.by == "vlade-rag/wiki-synthesis"
    assert page.verified[0].by == "human:pastor"
    assert page.status == "stable"
    assert page.stale_after == "2027-11-25T00:00:00Z"


def test_parse_page_requires_type() -> None:
    try:
        parse_page("---\ntitle: Sem tipo\n---\n\nTexto.", "erro.md")
    except InvalidArgument as exc:
        assert "type" in str(exc)
    else:
        raise AssertionError("A page without type must be rejected.")


def test_render_page_round_trip() -> None:
    page = parse_page(_PAGE, "teologia/batismo.md")
    rendered = render_page(page)
    again = parse_page(rendered, page.path)
    assert again == page


def test_validate_bundle_reports_missing_type(tmp_path: object) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    (root / "index.md").write_text("# Indice\n", encoding="utf-8")
    (root / "ok.md").write_text("---\ntype: Topic\n---\n\nTexto.", encoding="utf-8")
    (root / "bad.md").write_text("---\ntitle: Sem tipo\n---\n\nTexto.", encoding="utf-8")
    problems = validate_bundle(root)
    assert len(problems) == 1
    assert "bad.md" in problems[0]


def test_markdown_parser_keeps_okf_metadata() -> None:
    import asyncio

    async def _run() -> None:
        raw = RawDocument(filename="batismo.md", mime_type="text/markdown", data=_PAGE.encode())
        parsed = await MarkdownParser().parse(raw)
        assert parsed.title == "Batismo"
        assert parsed.metadata["okf_type"] == "Topic"
        assert parsed.metadata["okf_title"] == "Batismo"
        assert parsed.text.startswith("# Batismo")
        assert "---" not in parsed.text

    asyncio.run(_run())


def test_wiki_page_defaults() -> None:
    page = WikiPage(path="conceito.md", type="Topic")
    assert page.status == "stable"
    assert page.tags == ()
    assert "type: Topic" in render_page(page)
