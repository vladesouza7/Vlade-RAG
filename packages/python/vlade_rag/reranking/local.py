"""Local reranker with a ``sentence-transformers`` cross-encoder (ADR-0008, ADR-0018).

The model runs in the process of the server, so no text leaves the machine. It needs the
``local-models`` extra (``sentence-transformers`` and PyTorch). The module imports without the
extra: ``sentence_transformers`` is imported when the model loads.

The default model, ``BAAI/bge-reranker-v2-m3``, has 567,755,777 parameters in 32-bit floats. The
weights alone take about 2.3 GB of memory. Load and scoring are blocking, so they run in a worker
thread and do not stop the event loop.
"""

from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from vlade_rag.core.domain import InvalidArgument, ProviderUnavailable, ScoredChunk

EXTRA_HINT = (
    'The local reranker needs the "local-models" extra: pip install "vlade-rag[local-models]"'
)


class CrossEncoderLike(Protocol):
    """The part of ``sentence_transformers.CrossEncoder`` that this adapter uses."""

    def predict(self, sentences: list[tuple[str, str]], *, batch_size: int = ...) -> Any: ...


Loader = Callable[[str], CrossEncoderLike]


def _default_loader(device: str | None, max_length: int) -> Loader:
    def load(model: str) -> CrossEncoderLike:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise InvalidArgument(EXTRA_HINT) from exc
        # CrossEncoder takes ``device=None`` to pick CUDA, MPS or CPU by itself.
        return CrossEncoder(model, device=device, max_length=max_length)  # type: ignore[no-any-return]

    return load


class SentenceTransformersReranker:
    name = "sentence-transformers"

    def __init__(
        self,
        model: str,
        *,
        device: str | None = None,
        batch_size: int = 16,
        max_length: int = 512,
        loader: Loader | None = None,
    ) -> None:
        """``loader`` replaces the model loader. Tests use it. Without it, the extra must exist."""
        if batch_size < 1 or max_length < 1:
            raise InvalidArgument("batch_size and max_length must be 1 or more.")
        if loader is None and importlib.util.find_spec("sentence_transformers") is None:
            raise InvalidArgument(EXTRA_HINT)
        self.model = model
        self.batch_size = batch_size
        self._load = loader or _default_loader(device, max_length)
        self._encoder: CrossEncoderLike | None = None
        self._lock = asyncio.Lock()

    async def _encoder_ready(self) -> CrossEncoderLike:
        # The first call loads the model. Calls at the same time wait for that load and do not
        # start another one.
        async with self._lock:
            if self._encoder is None:
                try:
                    self._encoder = await asyncio.to_thread(self._load, self.model)
                except OSError as exc:  # no disk space, no network for the first download
                    raise ProviderUnavailable(
                        f"The local reranker could not load '{self.model}': {exc}"
                    ) from exc
            return self._encoder

    async def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        if not candidates:
            return []
        if top_n < 1:
            raise InvalidArgument("top_n must be 1 or more.")
        encoder = await self._encoder_ready()
        pairs = [(query, c.chunk.text) for c in candidates]
        try:
            raw = await asyncio.to_thread(encoder.predict, pairs, batch_size=self.batch_size)
            scores = [float(s) for s in raw]
        except (RuntimeError, ValueError, TypeError) as exc:
            raise ProviderUnavailable(f"The local reranker failed: {exc}") from exc
        if len(scores) != len(candidates):
            raise ProviderUnavailable("The local reranker returned a wrong number of scores.")
        # The index is the tie-break, so equal scores keep the order of the candidates.
        order = sorted(range(len(candidates)), key=lambda i: (-scores[i], i))
        return [
            ScoredChunk(candidates[i].chunk, scores[i], rank, "rerank")
            for rank, i in enumerate(order[: min(top_n, len(candidates))], start=1)
        ]
