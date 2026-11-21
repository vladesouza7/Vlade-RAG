"""The helpers of ``scripts/benchmarks/bench.py`` (roadmap 3.10). No database and no network."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from vlade_rag.core.domain import KnowledgeBase, KnowledgeBaseConfig

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).parents[2]


def load_bench() -> ModuleType:
    path = ROOT / "scripts" / "benchmarks" / "bench.py"
    spec = importlib.util.spec_from_file_location("bench", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load_bench()


def kb() -> KnowledgeBase:
    return KnowledgeBase(
        id=uuid4(),
        tenant_id=uuid4(),
        slug="k",
        name="k",
        config=KnowledgeBaseConfig(),
        active_embedding_space_id=uuid4(),
    )


def options(**values: object) -> argparse.Namespace:
    base = {
        "rerank_model": None,
        "rerank_provider": "openrouter",
        "candidates": 50,
        "top_k": 8,
        "query_transform": None,
        "retrievers": None,
    }
    return argparse.Namespace(**{**base, **values})


def test_percentile_is_the_nearest_rank() -> None:
    values = list(range(1, 101))  # 1 to 100
    assert bench.percentile(values, 50) == 50
    assert bench.percentile(values, 95) == 95
    assert bench.percentile(values, 99) == 99
    assert bench.percentile(values, 100) == 100
    assert bench.percentile([7.0], 95) == 7.0
    assert bench.percentile([5, 1, 3], 50) == 3  # it sorts first
    # With 20 values the p95 is the 19th: one value in twenty is above it.
    assert bench.percentile(list(range(1, 21)), 95) == 19


def test_percentile_of_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="no values"):
        bench.percentile([], 95)


def test_summarize_reports_milliseconds() -> None:
    summary = bench.summarize([0.1, 0.2, 0.3, 0.4])
    assert summary["n"] == 4
    assert summary["p50_ms"] == 200.0 and summary["max_ms"] == 400.0
    assert summary["mean_ms"] == 250.0


async def test_the_tracer_adds_each_span_to_the_bucket_of_the_request() -> None:
    tracer = bench.RecordingTracer()
    bucket: dict[str, float] = {}
    token = bench._bucket.set(bucket)
    try:
        with tracer.span("fusion"):
            await asyncio.sleep(0.01)
        with tracer.span("fusion"):  # a second span of the same name adds up
            await asyncio.sleep(0.01)
    finally:
        bench._bucket.reset(token)
    assert 0.015 < bucket["fusion"] < 0.5
    with tracer.span("outside"):  # no bucket: nothing is recorded and nothing fails
        pass
    assert "outside" not in bucket


async def test_requests_at_the_same_time_do_not_share_a_bucket() -> None:
    tracer = bench.RecordingTracer()

    async def request(delay: float) -> dict[str, float]:
        bucket: dict[str, float] = {}
        token = bench._bucket.set(bucket)
        try:
            with tracer.span("rerank"):
                await asyncio.sleep(delay)
        finally:
            bench._bucket.reset(token)
        return bucket

    slow, fast = await asyncio.gather(request(0.08), request(0.01))
    assert slow["rerank"] > 0.07 and fast["rerank"] < 0.07


async def test_timed_embeddings_records_queries_and_counts_documents() -> None:
    class Inner:
        dimension = 4

        async def embed_query(self, text: str) -> list[float]:
            return [0.0] * 4

        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 4 for _ in texts]

    timed = bench.TimedEmbeddings(Inner())
    bucket: dict[str, float] = {}
    token = bench._bucket.set(bucket)
    try:
        assert await timed.embed_query("q") == [0.0] * 4
    finally:
        bench._bucket.reset(token)
    await timed.embed_documents(["a", "b", "c"])
    assert "embed_query" in bucket
    assert timed.documents == 3 and timed.seconds >= 0.0
    assert timed.dimension == 4  # other attributes come from the wrapped provider


def test_with_options_changes_a_copy_and_leaves_the_base_alone() -> None:
    base = kb()
    changed = bench.with_options(
        base,
        options(
            rerank_model="mongodb/rerank-2.5", query_transform="hyde", retrievers="dense,fuzzy"
        ),
    )
    retrieval = changed.config.retrieval
    assert retrieval.rerank.enabled and retrieval.rerank.model == "mongodb/rerank-2.5"
    assert retrieval.rerank.top_n == 8 and retrieval.rerank.candidates == 50
    assert retrieval.query_transform == "hyde"
    assert retrieval.retrievers == ("dense", "fuzzy")
    assert not base.config.retrieval.rerank.enabled  # the base is not changed
    assert base.config.retrieval.query_transform == "none"
    assert bench.with_options(base, options()) is base  # no option: the same object


def test_questions_takes_the_first_n_and_refuses_a_short_file(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text(
        "".join(json.dumps({"question": f"pergunta {i}"}) + "\n" for i in range(5)),
        encoding="utf-8",
    )
    assert bench.questions(str(path), 3) == ["pergunta 0", "pergunta 1", "pergunta 2"]
    with pytest.raises(SystemExit):
        bench.questions(str(path), 6)


def test_read_sources_needs_markdown_files(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        bench.read_sources(str(tmp_path))
    (tmp_path / "b.md").write_text("segundo", encoding="utf-8")
    (tmp_path / "a.md").write_text("primeiro", encoding="utf-8")
    assert bench.read_sources(str(tmp_path)) == [("a.md", "primeiro"), ("b.md", "segundo")]


async def test_the_instant_llm_answers_with_a_citation() -> None:
    llm = bench.InstantLLM()
    assert "[1]" in (await llm.generate([], None)).text
    parts = [d.text async for d in llm.stream([], None)]
    assert parts == ["Resposta [1]."]


def test_build_documents_one_copy_of_every_file_per_replica() -> None:
    sources = [("a.md", "texto a"), ("b.md", "texto b")]
    documents = bench.build_documents(sources, replicas=2, start_replica=5, pages_per_document=0)
    assert [name for name, _ in documents] == [
        "r00005-a.md",
        "r00005-b.md",
        "r00006-a.md",
        "r00006-b.md",
    ]
    assert documents[0][1] == "<!-- replica 5 -->\ntexto a"
    assert len({text for _, text in documents}) == 4  # no two documents are the same


def test_build_documents_long_documents_have_the_pages_asked() -> None:
    body = "palavra " * 200  # 1600 characters
    sources = [("a.md", body), ("b.md", body + "x")]
    documents = bench.build_documents(sources, replicas=3, start_replica=0, pages_per_document=10)
    assert [name for name, _ in documents] == [f"r0000{i}-long.md" for i in range(3)]
    for _, text in documents:
        assert 10 * bench.PAGE_CHARS <= len(text) < 10 * bench.PAGE_CHARS + 2 * len(body) + 100
    assert len({text for _, text in documents}) == 3
