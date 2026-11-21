"""The local reranker (roadmap 3.1, ADR-0008, ADR-0018). No model and no network: a fake encoder."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from vlade_rag.bootstrap import build_runtime
from vlade_rag.core.config import Settings
from vlade_rag.core.domain import Chunk, InvalidArgument, ProviderUnavailable, ScoredChunk
from vlade_rag.core.domain.kb_config import RerankConfig
from vlade_rag.core.ports import Reranker
from vlade_rag.reranking import local
from vlade_rag.reranking.local import SentenceTransformersReranker

pytestmark = pytest.mark.anyio


class FakeEncoder:
    """Scores a pair with ``score(query, text)`` and records every call."""

    def __init__(self, score: Callable[[str, str], float] | None = None) -> None:
        self.score = score or (lambda query, text: float(len(text)))
        self.calls: list[tuple[list[tuple[str, str]], int]] = []
        self.threads: set[int] = set()

    def predict(self, sentences: list[tuple[str, str]], *, batch_size: int = 32) -> Any:
        self.threads.add(threading.get_ident())
        self.calls.append((sentences, batch_size))
        return [self.score(q, t) for q, t in sentences]


class Loads:
    """A loader that counts how many times the model loads."""

    def __init__(self, encoder: Any) -> None:
        self.encoder = encoder
        self.models: list[str] = []

    def __call__(self, model: str) -> Any:
        self.models.append(model)
        return self.encoder


def candidates(*texts: str) -> list[ScoredChunk]:
    tenant, kb, doc, version = uuid4(), uuid4(), uuid4(), uuid4()
    return [
        ScoredChunk(
            Chunk(uuid4(), tenant, kb, doc, version, i, text, 5, 0, len(text)),
            score=1.0 / (i + 1),
            rank=i + 1,
            retriever="fusion",
        )
        for i, text in enumerate(texts)
    ]


def reranker(encoder: Any = None, **options: Any) -> tuple[SentenceTransformersReranker, Loads]:
    loads = Loads(encoder or FakeEncoder())
    return SentenceTransformersReranker("some/model", loader=loads, **options), loads


async def test_orders_by_the_score_of_the_encoder() -> None:
    # The score is the length of the text: the longest text is the most relevant.
    items = candidates("a", "ccc", "bb")
    ranker, _ = reranker()
    out = await ranker.rerank("pergunta", items, 3)

    assert [c.chunk.text for c in out] == ["ccc", "bb", "a"]
    assert [c.rank for c in out] == [1, 2, 3]
    assert [c.score for c in out] == [3.0, 2.0, 1.0]
    assert {c.retriever for c in out} == {"rerank"}
    assert isinstance(ranker, Reranker)


async def test_sends_one_pair_of_query_and_text_per_candidate() -> None:
    encoder = FakeEncoder()
    ranker, _ = reranker(encoder, batch_size=4)
    await ranker.rerank("qual o prazo?", candidates("um", "dois"), 2)

    pairs, batch_size = encoder.calls[0]
    assert pairs == [("qual o prazo?", "um"), ("qual o prazo?", "dois")]
    assert batch_size == 4


async def test_top_n_cuts_the_list_and_is_capped_at_the_number_of_candidates() -> None:
    ranker, _ = reranker()
    assert len(await ranker.rerank("q", candidates("a", "bb", "ccc"), 2)) == 2
    assert len(await ranker.rerank("q", candidates("a", "bb"), 50)) == 2


async def test_equal_scores_keep_the_order_of_the_candidates() -> None:
    ranker, _ = reranker(FakeEncoder(lambda q, t: 1.0))
    out = await ranker.rerank("q", candidates("a", "b", "c"), 3)
    assert [c.chunk.text for c in out] == ["a", "b", "c"]


async def test_the_model_loads_once_and_only_when_needed() -> None:
    ranker, loads = reranker()
    assert loads.models == []  # building the reranker does not load the model
    assert await ranker.rerank("q", [], 5) == []
    assert loads.models == []  # an empty list does not load it either
    await ranker.rerank("q", candidates("a"), 1)
    await ranker.rerank("q", candidates("b"), 1)
    assert loads.models == ["some/model"]


async def test_calls_at_the_same_time_load_the_model_once() -> None:
    ranker, loads = reranker()
    await asyncio.gather(*(ranker.rerank("q", candidates("a", "bb"), 2) for _ in range(5)))
    assert loads.models == ["some/model"]


async def test_scoring_does_not_run_on_the_thread_of_the_event_loop() -> None:
    encoder = FakeEncoder()
    ranker, _ = reranker(encoder)
    await ranker.rerank("q", candidates("a", "bb"), 2)
    assert encoder.threads and threading.get_ident() not in encoder.threads


async def test_a_wrong_number_of_scores_is_a_provider_error() -> None:
    class Short:
        def predict(self, sentences: list[tuple[str, str]], *, batch_size: int = 32) -> Any:
            return [1.0]

    ranker, _ = reranker(Short())
    with pytest.raises(ProviderUnavailable, match="wrong number of scores"):
        await ranker.rerank("q", candidates("a", "b"), 2)


@pytest.mark.parametrize("error", [RuntimeError("out of memory"), ValueError("bad input")])
async def test_a_failure_of_the_encoder_is_a_provider_error(error: Exception) -> None:
    class Broken:
        def predict(self, sentences: list[tuple[str, str]], *, batch_size: int = 32) -> Any:
            raise error

    ranker, _ = reranker(Broken())
    with pytest.raises(ProviderUnavailable, match="The local reranker failed"):
        await ranker.rerank("q", candidates("a"), 1)


async def test_a_model_that_cannot_be_downloaded_is_a_provider_error() -> None:
    def load(model: str) -> Any:
        raise OSError("no network")

    ranker = SentenceTransformersReranker("some/model", loader=load)
    with pytest.raises(ProviderUnavailable, match="could not load 'some/model': no network"):
        await ranker.rerank("q", candidates("a"), 1)


async def test_invalid_options_are_refused() -> None:
    ranker, _ = reranker()
    with pytest.raises(InvalidArgument):
        await ranker.rerank("q", candidates("a"), 0)
    with pytest.raises(InvalidArgument):
        SentenceTransformersReranker("m", batch_size=0, loader=Loads(FakeEncoder()))
    with pytest.raises(InvalidArgument):
        SentenceTransformersReranker("m", max_length=0, loader=Loads(FakeEncoder()))


def test_without_the_extra_the_error_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(InvalidArgument, match=r"vlade-rag\[local-models\]"):
        SentenceTransformersReranker("some/model")


async def test_the_runtime_builds_the_local_reranker_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VLADE_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_OBJECT_STORAGE__BACKEND", "memory")
    monkeypatch.setenv("VLADE_PROVIDERS__LOCAL_MODELS__DEVICE", "cpu")
    monkeypatch.setenv("VLADE_PROVIDERS__LOCAL_MODELS__BATCH_SIZE", "8")
    monkeypatch.setattr(local.importlib.util, "find_spec", lambda name: object())
    runtime = await build_runtime(Settings(), load_plugins=False)
    try:
        resolve = runtime.deps.rerankers
        assert resolve is not None
        config = RerankConfig(provider="sentence-transformers", model="BAAI/bge-reranker-v2-m3")
        ranker = resolve(config)
        assert isinstance(ranker, SentenceTransformersReranker)
        assert ranker.model == "BAAI/bge-reranker-v2-m3" and ranker.batch_size == 8
        assert resolve(config) is ranker  # one instance, so the model loads once per process
    finally:
        await runtime.aclose()


def test_the_default_settings_of_the_local_models() -> None:
    options = Settings().providers.local_models
    assert (options.device, options.batch_size, options.max_length) == (None, 16, 512)
