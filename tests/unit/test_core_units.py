"""Unit tests of smaller core pieces and failure paths."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from tests.conftest import World
from vlade_rag.core.application import CreateKnowledgeBase, GetIngestionStatus, SubmitIngestion
from vlade_rag.core.application.ingestion import normalize_parsed
from vlade_rag.core.application.mime import DOCX, PDF, resolve_mime_type
from vlade_rag.core.domain import (
    InvalidArgument,
    JobStatus,
    KnowledgeBaseConfig,
    NotFound,
    ParsedDocument,
    ProviderUnavailable,
    RawDocument,
    Role,
    TenantContext,
    UnsupportedFilter,
    matches,
    parse_filter,
    uuid7,
)
from vlade_rag.core.domain.kb_config import ChunkingConfig, EmbeddingsConfig
from vlade_rag.core.registry import DuplicatePluginError, PluginSpec, Registry
from vlade_rag.ingestion.chunking import NativeTextNormalizer
from vlade_rag.ingestion.parsers.docling import DoclingParser
from vlade_rag.knowledge.filesystem import FilesystemObjectStorage

# ---------------------------------------------------------------- filters


def test_parse_filter_and_matches() -> None:
    meta = {"area": "rh", "nivel": 2, "tags": "x"}
    assert parse_filter(None) is None
    assert matches(parse_filter({"area": "rh"}), meta)
    assert not matches(parse_filter({"area": "ti"}), meta)
    assert matches(parse_filter({"nivel": {"in": [1, 2]}}), meta)
    assert matches(parse_filter({"tags": {"exists": True}}), meta)
    assert not matches(parse_filter({"outro": {"exists": True}}), meta)
    assert matches(parse_filter({"$or": [{"area": "ti"}, {"area": "rh"}]}), meta)
    assert not matches(parse_filter({"$and": [{"area": "rh"}, {"nivel": 3}]}), meta)
    assert matches(parse_filter({"area": "rh", "nivel": 2}), meta)


@pytest.mark.parametrize(
    "raw",
    [{"$not": []}, {"$and": []}, {"area": {"gt": 1}}, {"area": {"exists": False}}],
)
def test_parse_filter_rejects_unsupported(raw: dict[str, Any]) -> None:
    with pytest.raises(UnsupportedFilter):
        parse_filter(raw)


# ---------------------------------------------------------------- configuration and documents


def test_requires_reindex() -> None:
    base = KnowledgeBaseConfig()
    assert base.requires_reindex(base) == "none"
    batch = base.model_copy(update={"embeddings": EmbeddingsConfig(batch_size=8)})
    assert base.requires_reindex(batch) == "none"
    model = base.model_copy(update={"embeddings": EmbeddingsConfig(model="e5", dimension=768)})
    assert base.requires_reindex(model) == "embeddings"
    chunking = base.model_copy(update={"chunking": ChunkingConfig(max_tokens=256)})
    assert base.requires_reindex(chunking) == "full"


def test_chunking_config_validation() -> None:
    with pytest.raises(ValueError):
        ChunkingConfig(max_tokens=100, overlap_tokens=100)


def test_page_and_section_lookup() -> None:
    doc = ParsedDocument(text="a" * 30, page_starts=(0, 10, 20))
    assert [doc.page_at(o) for o in (0, 9, 10, 25)] == [1, 1, 2, 3]
    assert ParsedDocument(text="x").page_at(0) is None


def test_normalize_parsed_keeps_pages_and_detects_sections() -> None:
    text = "# Um\n\n texto   da  página 1\n## Dois\npágina 2"
    parsed = ParsedDocument(text=text, page_starts=(0, text.index("## Dois")))
    out = normalize_parsed(parsed, NativeTextNormalizer())
    assert out.text.startswith("# Um\n\ntexto da página 1")
    assert out.page_at(out.text.index("página 2")) == 2
    assert [(s.title, s.level) for s in out.sections] == [("Um", 1), ("Dois", 2)]


def test_resolve_mime_type() -> None:
    assert resolve_mime_type("a.md", None, b"# x") == "text/markdown"
    assert resolve_mime_type("a.bin", "text/plain; charset=utf-8", b"x") == "text/plain"
    assert resolve_mime_type("a.pdf", "application/octet-stream", b"%PDF-1.7") == PDF
    assert resolve_mime_type("a.docx", "", b"PK\x03\x04rest") == DOCX
    for name, data in [
        ("a.xyz", b"x"),
        ("a.docx", b"no"),
        ("a.txt", b"\x00\x01"),
        ("a.txt", b"\xff"),
    ]:
        with pytest.raises(InvalidArgument):
            resolve_mime_type(name, None, data)


# ---------------------------------------------------------------- docling parser (fake converter)


class _FakeDoc:
    name = "relatorio"
    pages: ClassVar[dict[int, object]] = {1: object(), 2: object()}

    def export_to_markdown(self, page_no: int | None = None) -> str:
        return {None: "tudo", 1: "# Capítulo\n\nprimeira página", 2: "segunda página"}[page_no]


class _FakeConverter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def convert(self, source: Any) -> Any:
        if self.fail:
            raise RuntimeError("broken pdf")
        assert source.name == "r.pdf"
        return SimpleNamespace(document=_FakeDoc())


@pytest.mark.anyio
async def test_docling_parser_pages() -> None:
    parsed = await DoclingParser(_FakeConverter()).parse(RawDocument("r.pdf", PDF, b"%PDF-1"))
    assert parsed.title == "relatorio"
    assert parsed.page_at(parsed.text.index("segunda")) == 2
    with pytest.raises(InvalidArgument, match="broken pdf"):
        await DoclingParser(_FakeConverter(fail=True)).parse(RawDocument("r.pdf", PDF, b"%PDF"))


@pytest.mark.anyio
async def test_pdf_ingestion_with_pages(world: World) -> None:
    world.deps.parsers = [*world.deps.parsers, DoclingParser(_FakeConverter())]
    await _kb(world)
    result = await SubmitIngestion(world.deps).execute(
        world.admin, knowledge_base="kb", raw=RawDocument("r.pdf", "", b"%PDF-1.7 data")
    )
    await world.drain_jobs()
    job = await GetIngestionStatus(world.deps).execute(world.reader, result.job.id)
    assert job.status == JobStatus.SUCCEEDED, job.error


# ---------------------------------------------------------------- ingestion failures


async def _kb(world: World) -> None:
    config = KnowledgeBaseConfig(embeddings=EmbeddingsConfig(provider="h", model="h", dimension=64))
    await CreateKnowledgeBase(world.deps).execute(world.admin, slug="kb", name="KB", config=config)


@pytest.mark.anyio
async def test_parser_error_fails_job_without_retry(world: World) -> None:
    class Broken:
        mime_types = frozenset({"text/plain"})

        async def parse(self, raw: RawDocument) -> ParsedDocument:
            raise InvalidArgument("unreadable")

    world.deps.parsers = [Broken()]
    await _kb(world)
    result = await SubmitIngestion(world.deps).execute(
        world.admin, knowledge_base="kb", raw=RawDocument("a.txt", "text/plain", b"x")
    )
    await world.drain_jobs()
    job = await GetIngestionStatus(world.deps).execute(world.reader, result.job.id)
    assert job.status == JobStatus.FAILED
    assert job.error and job.error["step"] == "extract" and job.error["code"] == "invalid_argument"
    assert [(s.name, s.status) for s in job.steps] == [("extract", JobStatus.FAILED)]


@pytest.mark.anyio
async def test_provider_outage_retries_then_fails(world: World) -> None:
    class Down:
        provider, model, dimension, max_batch_size = "down", "m", 64, 8

        async def embed_documents(self, texts: Any) -> list[list[float]]:
            raise ProviderUnavailable("offline")

        async def embed_query(self, text: str) -> list[float]:
            raise ProviderUnavailable("offline")

    world.deps.embeddings = lambda cfg: Down()
    await _kb(world)
    result = await SubmitIngestion(world.deps).execute(
        world.admin, knowledge_base="kb", raw=RawDocument("a.txt", "text/plain", b"texto")
    )
    assert await world.drain_jobs() == world.deps.limits.job_max_attempts
    job = await GetIngestionStatus(world.deps).execute(world.reader, result.job.id)
    assert job.status == JobStatus.FAILED
    assert job.attempt == world.deps.limits.job_max_attempts
    assert job.error and job.error["step"] == "embed"


@pytest.mark.anyio
async def test_empty_document_fails(world: World) -> None:
    await _kb(world)
    result = await SubmitIngestion(world.deps).execute(
        world.admin, knowledge_base="kb", raw=RawDocument("a.txt", "text/plain", b"   \n ")
    )
    await world.drain_jobs()
    job = await GetIngestionStatus(world.deps).execute(world.reader, result.job.id)
    assert job.status == JobStatus.FAILED and job.error and job.error["step"] == "normalize"


@pytest.mark.anyio
async def test_unknown_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound):
        await GetIngestionStatus(world.deps).execute(world.reader, uuid7())


# ---------------------------------------------------------------- worker loop


@pytest.mark.anyio
async def test_worker_run_processes_and_stops(world: World) -> None:
    from vlade_rag.bootstrap import Runtime
    from vlade_rag.core.config import Settings
    from vlade_rag.ingestion.worker import Worker

    await _kb(world)
    for i in range(3):
        await SubmitIngestion(world.deps).execute(
            world.admin,
            knowledge_base="kb",
            raw=RawDocument(f"d{i}.txt", "text/plain", f"documento {i}".encode()),
        )
    runtime = Runtime(Settings(), world.deps, world.tenants, Registry())
    worker = Worker(runtime, worker_id="w", concurrency=2, poll_interval=0.01, lease_seconds=30)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    for _ in range(200):
        if await world.job_queue.claim("probe", 1) is None:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert await world.job_queue.claim("probe", 1) is None


@pytest.mark.anyio
async def test_requeue_expired_jobs(world: World) -> None:
    await _kb(world)
    await SubmitIngestion(world.deps).execute(
        world.admin, knowledge_base="kb", raw=RawDocument("a.txt", "text/plain", b"x y")
    )
    claimed = await world.job_queue.claim("crashed-worker", 0)
    assert claimed is not None
    await asyncio.sleep(0.01)
    assert await world.job_queue.requeue_expired(max_attempts=3) == 1
    again = await world.job_queue.claim("w2", 30)
    assert again is not None and again.job.attempt == 2


# ---------------------------------------------------------------- registry and storage


def test_registry() -> None:
    registry = Registry()
    registry.register(PluginSpec("llm", "x", lambda: "made"))
    assert registry.create("llm", "x") == "made"
    assert registry.names("llm") == ["x"]
    with pytest.raises(DuplicatePluginError):
        registry.register(PluginSpec("llm", "x", lambda: None))
    with pytest.raises(InvalidArgument, match="Available: x"):
        registry.get("llm", "y")
    assert registry.load_entry_points("vlade_rag.no_such_group") == 0


@pytest.mark.anyio
async def test_filesystem_storage(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path)
    ctx = TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")
    await storage.put(ctx, "kb/1/doc/a", b"data", "text/plain")
    await storage.put(ctx, "kb/1/doc/b", b"more", "text/plain")
    assert await storage.get(ctx, "kb/1/doc/a") == b"data"
    assert (tmp_path / str(ctx.tenant_id) / "kb/1/doc/a").exists()
    other = TenantContext(uuid7(), uuid7(), frozenset({Role.ADMIN}), "library")
    with pytest.raises(NotFound):
        await storage.get(other, "kb/1/doc/a")
    for bad in ("../x", "/etc/passwd", ""):
        with pytest.raises(InvalidArgument):
            await storage.get(ctx, bad)
    assert await storage.delete_prefix(ctx, "kb/1/") == 2
    assert await storage.delete_prefix(ctx, "kb/1/") == 0
    await storage.delete(ctx, "kb/1/doc/a")
