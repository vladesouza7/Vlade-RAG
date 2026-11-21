"""Benchmarks of ROADMAP task 3.10 (RNF-01 to RNF-04).

The script runs the library itself (no HTTP) against the PostgreSQL and the providers set in the
environment, the same way the CLI does. A recording tracer gives the time of each stage of a
request. The caches are off on purpose: every request is cold.

Subcommands:

- ``search``: latency of ``Search.run`` (RNF-01 without reranker, RNF-02 with one) and the cost of
  the query transforms. ``--concurrency`` gives the throughput of searches.
- ``ttft``: time to the first token of ``AnswerQuery.stream`` with an LLM that answers at once, so
  the time of the remote LLM is not in the number (RNF-03).
- ``ingest``: throughput of one ingestion worker (RNF-04). The embeddings provider of the base
  should be ``hashing``, so the time of the remote embeddings is not in the number. The script
  also reports the time spent in the embeddings provider, to subtract it.
- ``info``: the machine and the database, for the header of a report.

Needs ``VLADE_API_KEY`` (an admin key) and the ``VLADE_*`` settings of the CLI.

Usage: python3 scripts/benchmarks/bench.py search --kb legal-ptbr-v2 --dataset FILE --n 100
Run it with the project environment (``uv run python scripts/benchmarks/bench.py ...``).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import contextvars
import json
import math
import os
import platform
import sys
import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from vlade_rag.bootstrap import Runtime, build_runtime
from vlade_rag.core.application import (
    AnswerDelta,
    AnswerQuery,
    CreateKnowledgeBase,
    RunIngestionJob,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.domain import (
    Conflict,
    Generation,
    GenerationDelta,
    KnowledgeBase,
    Query,
    RawDocument,
    TenantContext,
)
from vlade_rag.core.domain.kb_config import RerankConfig

PAGE_CHARS = 3000  # a "page" of RNF-04: 3000 characters, about 500 words
STAGES = (
    "embed_query",
    "query_transform",
    "retrieval.dense",
    "retrieval.lexical",
    "retrieval.fuzzy",
    "retrieval.bm25",
    "fusion",
    "rerank",
    "context_assembly",
)

_bucket: contextvars.ContextVar[dict[str, float] | None] = contextvars.ContextVar(
    "bucket", default=None
)


def record(name: str, seconds: float) -> None:
    bucket = _bucket.get()
    if bucket is not None:
        bucket[name] = bucket.get(name, 0.0) + seconds


class _Span:
    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def add_event(self, name: str, attributes: Any = None) -> None:
        return None


class RecordingTracer:
    """A tracer that adds the duration of each span to the bucket of the current request."""

    @contextmanager
    def span(self, name: str, attributes: Any = None) -> Iterator[_Span]:
        started = time.perf_counter()
        try:
            yield _Span()
        finally:
            record(name, time.perf_counter() - started)

    def current_trace_id(self) -> str | None:
        return None


class TimedEmbeddings:
    """Wraps an embeddings provider and records its time."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.documents = 0
        self.seconds = 0.0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def embed_query(self, text: str) -> list[float]:
        started = time.perf_counter()
        try:
            vector: list[float] = await self.inner.embed_query(text)
            return vector
        finally:
            record("embed_query", time.perf_counter() - started)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        started = time.perf_counter()
        try:
            vectors: list[list[float]] = await self.inner.embed_documents(texts)
            return vectors
        finally:
            self.seconds += time.perf_counter() - started
            self.documents += len(texts)


class InstantLLM:
    """An LLM that answers at once. It leaves the time of the remote LLM out of the number."""

    name = "instant"

    async def generate(self, messages: Any, params: Any) -> Generation:
        return Generation(text="Resposta [1].", model="instant")

    async def stream(self, messages: Any, params: Any) -> AsyncIterator[GenerationDelta]:
        yield GenerationDelta(text="Resposta [1].")


class OverriddenRepository:
    """A repository whose knowledge base has the retrieval settings of this run."""

    def __init__(self, inner: Any, override: Callable[[KnowledgeBase], KnowledgeBase]) -> None:
        self.inner = inner
        self.override = override

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def get_knowledge_base(self, ctx: TenantContext, slug: str) -> KnowledgeBase:
        kb: KnowledgeBase = await self.inner.get_knowledge_base(ctx, slug)
        return self.override(kb)


def percentile(values: Sequence[float], p: float) -> float:
    """The nearest-rank percentile: the smallest value with at least ``p`` percent below it."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(values: Sequence[float]) -> dict[str, float]:
    ms = [v * 1000 for v in values]
    return {
        "n": len(ms),
        "p50_ms": round(percentile(ms, 50), 1),
        "p95_ms": round(percentile(ms, 95), 1),
        "p99_ms": round(percentile(ms, 99), 1),
        "mean_ms": round(sum(ms) / len(ms), 1),
        "max_ms": round(max(ms), 1),
    }


def questions(path: str, n: int) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    found = [json.loads(line)["question"] for line in lines if line.strip()]
    if len(found) < n:
        raise SystemExit(f"The dataset has {len(found)} questions and --n is {n}.")
    return found[:n]


def read_sources(folder: str) -> list[tuple[str, str]]:
    files = sorted(Path(folder).glob("*.md"))
    if not files:
        raise SystemExit(f"No .md file in {folder}.")
    return [(p.name, p.read_text(encoding="utf-8")) for p in files]


def build_documents(
    sources: Sequence[tuple[str, str]],
    replicas: int,
    start_replica: int,
    pages_per_document: int,
) -> list[tuple[str, str]]:
    """The documents to submit, as ``(file name, text)``.

    Without ``pages_per_document``, every replica is one copy of every source file. With it, every
    replica is one long document of that many pages, built from the source files in turn. The first
    line of each document names its replica, so no two documents have the same content and none is
    skipped as unchanged.
    """
    documents: list[tuple[str, str]] = []
    for replica in range(start_replica, start_replica + replicas):
        header = f"<!-- replica {replica} -->\n"
        if pages_per_document <= 0:
            documents += [(f"r{replica:05d}-{name}", header + body) for name, body in sources]
            continue
        target, size, index, parts = pages_per_document * PAGE_CHARS, 0, replica, []
        while size < target:
            body = sources[index % len(sources)][1]
            parts.append(body)
            size += len(body) + 2
            index += 1
        documents.append((f"r{replica:05d}-long.md", header + "\n\n".join(parts)))
    return documents


def with_options(kb: KnowledgeBase, args: argparse.Namespace) -> KnowledgeBase:
    """The knowledge base with the retrieval settings given on the command line."""
    retrieval = kb.config.retrieval
    updates: dict[str, Any] = {}
    if getattr(args, "rerank_model", None):
        rerank = RerankConfig(
            enabled=True,
            provider=args.rerank_provider,
            model=args.rerank_model,
            candidates=args.candidates,
            top_n=args.top_k,
        )
        updates["rerank"] = rerank
    if getattr(args, "query_transform", None):
        updates["query_transform"] = args.query_transform
    if getattr(args, "retrievers", None):
        updates["retrievers"] = tuple(r.strip() for r in args.retrievers.split(","))
    if not updates:
        return kb
    retrieval = retrieval.model_copy(update=updates)
    return replace(kb, config=kb.config.model_copy(update={"retrieval": retrieval}))


async def open_runtime() -> tuple[Runtime, TenantContext]:
    key = os.environ.get("VLADE_API_KEY")
    if not key:
        raise SystemExit("Set VLADE_API_KEY with an admin key ('vlade-rag key create').")
    runtime = await build_runtime()
    ctx = await runtime.tenants.authenticate(key, interface="benchmark")
    runtime.deps.cache = None  # every request is cold
    runtime.deps.tracer = RecordingTracer()
    original = runtime.deps.embeddings
    timed: dict[str, TimedEmbeddings] = {}

    def embeddings(cfg: Any) -> TimedEmbeddings:
        key_ = cfg.model_dump_json()
        if key_ not in timed:
            timed[key_] = TimedEmbeddings(original(cfg))
        return timed[key_]

    runtime.deps.embeddings = embeddings
    runtime.timed_embeddings = timed  # type: ignore[attr-defined]
    return runtime, ctx


def stage_report(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for stage in STAGES:
        values = [row[stage] for row in rows if stage in row]
        if values:
            report[stage] = summarize(values) | {"requests": len(values)}
    return report


def environment() -> dict[str, Any]:
    memory = "unknown"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                memory = f"{int(line.split()[1]) / 1024 / 1024:.1f} GB"
    except OSError:
        pass
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
        "memory": memory,
    }


def emit(report: dict[str, Any], output: str | None) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")


# ---------------------------------------------------------------------- search


async def run_search(args: argparse.Namespace) -> None:
    runtime, ctx = await open_runtime()
    try:
        kb = with_options(await runtime.deps.repository.get_knowledge_base(ctx, args.kb), args)
        texts = questions(args.dataset, args.n + args.warmup)
        search = Search(runtime.deps)
        rows: list[dict[str, float]] = []
        failures: list[str] = []

        async def one(text: str, record_it: bool) -> None:
            bucket: dict[str, float] = {}
            token = _bucket.set(bucket)
            started = time.perf_counter()
            try:
                await search.run(ctx, kb, Query(text, kb.id), args.top_k)
            except Exception as exc:  # a failed request counts as a failure, not as a latency
                failures.append(type(exc).__name__)
                return
            finally:
                _bucket.reset(token)
            if record_it:
                rows.append({"total": time.perf_counter() - started, **bucket})

        for text in texts[: args.warmup]:  # connections, pools and first-call costs
            await one(text, False)
        measured = texts[args.warmup :]
        wall = time.perf_counter()
        semaphore = asyncio.Semaphore(args.concurrency)

        async def limited(text: str) -> None:
            async with semaphore:
                await one(text, True)

        await asyncio.gather(*(limited(t) for t in measured))
        wall = time.perf_counter() - wall
        retrieval = kb.config.retrieval
        report = {
            "benchmark": "search",
            "knowledge_base": args.kb,
            "retrievers": list(retrieval.retrievers),
            "rerank": retrieval.rerank.model if retrieval.rerank.enabled else None,
            "query_transform": retrieval.query_transform,
            "top_k": args.top_k,
            "candidates": retrieval.rerank.candidates if retrieval.rerank.enabled else None,
            "concurrency": args.concurrency,
            "requests": len(measured),
            "failures": len(failures),
            "failure_types": sorted(set(failures)),
            "throughput_per_second": round(len(rows) / wall, 2) if rows else 0.0,
            "latency": summarize([r["total"] for r in rows]) if rows else None,
            "stages": stage_report(rows),
            "caches": "off",
            "environment": environment(),
        }
        emit(report, args.output)
    finally:
        await runtime.aclose()


# ------------------------------------------------------------------------ ttft


async def run_ttft(args: argparse.Namespace) -> None:
    runtime, ctx = await open_runtime()
    try:
        deps = runtime.deps
        deps.llms = lambda cfg: InstantLLM()  # type: ignore[assignment,return-value]
        deps.repository = OverriddenRepository(  # type: ignore[assignment]
            deps.repository, lambda kb: with_options(kb, args)
        )
        texts = questions(args.dataset, args.n + args.warmup)
        answer = AnswerQuery(deps)
        rows: list[dict[str, float]] = []
        empty = 0

        async def one(text: str, record_it: bool) -> None:
            nonlocal empty
            bucket: dict[str, float] = {}
            token = _bucket.set(bucket)
            started = time.perf_counter()
            first: float | None = None
            try:
                async for event in answer.stream(
                    ctx, knowledge_base=args.kb, question=text, top_k=args.top_k
                ):
                    if isinstance(event, AnswerDelta):
                        first = time.perf_counter() - started
                        break
            finally:
                _bucket.reset(token)
            if record_it:
                if first is None:
                    empty += 1
                else:
                    rows.append({"total": first, **bucket})

        for text in texts[: args.warmup]:
            await one(text, False)
        for text in texts[args.warmup :]:
            await one(text, True)
        retrieval = (await deps.repository.get_knowledge_base(ctx, args.kb)).config.retrieval
        report = {
            "benchmark": "ttft",
            "what": "time to the first answer token, with an LLM that answers at once",
            "knowledge_base": args.kb,
            "rerank": retrieval.rerank.model if retrieval.rerank.enabled else None,
            "query_transform": retrieval.query_transform,
            "requests": len(rows) + empty,
            "no_token": empty,
            "ttft": summarize([r["total"] for r in rows]) if rows else None,
            "stages": stage_report(rows),
            "caches": "off",
            "environment": environment(),
        }
        emit(report, args.output)
    finally:
        await runtime.aclose()


# ---------------------------------------------------------------------- ingest


async def run_ingest(args: argparse.Namespace) -> None:
    runtime, ctx = await open_runtime()
    try:
        deps = runtime.deps
        config = {
            "language": "pt",
            "chunking": {"strategy": "markdown", "max_tokens": 400, "overlap_tokens": 40},
            "embeddings": {
                "provider": "hashing",
                "model": "hashing-v1",
                "dimension": args.dimension,
                "batch_size": 64,
            },
        }
        with contextlib.suppress(Conflict):
            await CreateKnowledgeBase(deps).execute(ctx, slug=args.kb, name=args.kb, config=config)
        documents = build_documents(
            read_sources(args.docs), args.replicas, args.start_replica, args.pages_per_document
        )
        submitted = len(documents)
        characters = sum(len(text) for _, text in documents)
        submit = SubmitIngestion(deps)
        for filename, text in documents:
            await submit.execute(
                ctx,
                knowledge_base=args.kb,
                raw=RawDocument(
                    filename=filename, mime_type="text/markdown", data=text.encode("utf-8")
                ),
            )
        timed: dict[str, TimedEmbeddings] = runtime.timed_embeddings  # type: ignore[attr-defined]
        runner = RunIngestionJob(deps)

        async def drain() -> int:
            """One job slot of the worker: claim a job, run it, and claim the next."""
            count = 0
            while (claimed := await deps.job_queue.claim("benchmark-worker", 600)) is not None:
                await runner.execute(claimed)
                count += 1
            return count

        wall = time.perf_counter()
        done = sum(await asyncio.gather(*(drain() for _ in range(args.concurrency))))
        wall = time.perf_counter() - wall
        embed_seconds = sum(t.seconds for t in timed.values())
        chunks = sum(t.documents for t in timed.values())
        pages = characters / PAGE_CHARS
        without_embeddings = wall - embed_seconds
        report = {
            "benchmark": "ingest",
            "knowledge_base": args.kb,
            "embeddings": f"hashing, {args.dimension} dimensions",
            "documents": submitted,
            "jobs_run": done,
            "characters": characters,
            "pages": round(pages, 1),
            "page_definition": f"{PAGE_CHARS} characters",
            "chunks": chunks,
            "worker": f"one worker process, {args.concurrency} job(s) at a time",
            "concurrency": args.concurrency,
            "seconds_total": round(wall, 2),
            "seconds_in_embeddings": round(embed_seconds, 2),
            "seconds_without_embeddings": round(without_embeddings, 2),
            "pages_per_second_total": round(pages / wall, 1),
            "pages_per_second_without_embeddings": round(pages / without_embeddings, 1),
            "documents_per_second_total": round(submitted / wall, 1),
            "chunks_per_second_total": round(chunks / wall, 1),
            "environment": environment(),
        }
        emit(report, args.output)
    finally:
        await runtime.aclose()


# ------------------------------------------------------------------------ info


async def run_info(args: argparse.Namespace) -> None:
    runtime, ctx = await open_runtime()
    try:
        counts: dict[str, Any] = {}
        db = getattr(runtime.deps.repository, "db", None)
        if db is not None:
            async with db.tenant(ctx) as conn:
                rows = await conn.fetch(
                    "SELECT kb.slug, count(DISTINCT d.id) AS documents,"
                    " count(c.id) AS chunks FROM knowledge_bases kb"
                    " LEFT JOIN documents d ON d.knowledge_base_id = kb.id"
                    " LEFT JOIN chunks c ON c.document_id = d.id"
                    " GROUP BY kb.slug ORDER BY kb.slug"
                )
                counts = {
                    r["slug"]: {"documents": r["documents"], "chunks": r["chunks"]} for r in rows
                }
                counts["_postgres"] = await conn.fetchval("SHOW server_version")
        emit({"benchmark": "info", "knowledge_bases": counts, "environment": environment()}, None)
    finally:
        await runtime.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--kb", required=True)
        p.add_argument("--output", help="Write the report (JSON) to this file.")

    def retrieval(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dataset", required=True, help="JSON Lines with a 'question' field.")
        p.add_argument("--n", type=int, default=100, help="Requests that count.")
        p.add_argument("--warmup", type=int, default=3, help="Requests that do not count.")
        p.add_argument("--top-k", type=int, default=8)
        p.add_argument("--rerank-model")
        p.add_argument("--rerank-provider", default="openrouter")
        p.add_argument("--candidates", type=int, default=50)
        p.add_argument("--query-transform")
        p.add_argument("--retrievers", help="For example dense,lexical,fuzzy.")

    search = sub.add_parser("search", help="Latency and throughput of Search.run.")
    common(search)
    retrieval(search)
    search.add_argument("--concurrency", type=int, default=1)
    search.set_defaults(run=run_search)

    ttft = sub.add_parser("ttft", help="Time to the first token, without the remote LLM.")
    common(ttft)
    retrieval(ttft)
    ttft.set_defaults(run=run_ttft)

    ingest = sub.add_parser("ingest", help="Ingestion throughput of one worker.")
    common(ingest)
    ingest.add_argument("--docs", required=True, help="Folder with .md files.")
    ingest.add_argument("--replicas", type=int, default=1, help="Copies of every file.")
    ingest.add_argument("--start-replica", type=int, default=0)
    ingest.add_argument("--dimension", type=int, default=1024)
    ingest.add_argument(
        "--pages-per-document",
        type=int,
        default=0,
        help="Make each replica one document of this many pages (0: one document per file).",
    )
    ingest.add_argument(
        "--concurrency", type=int, default=2, help="Jobs at a time (the worker default is 2)."
    )
    ingest.set_defaults(run=run_ingest)

    info = sub.add_parser("info", help="Documents and chunks of every base.")
    info.add_argument("--kb", default="", help="Not used.")
    info.set_defaults(run=run_info)

    args = parser.parse_args()
    asyncio.run(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
