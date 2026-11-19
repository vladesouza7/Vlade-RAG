"""Bridge to the optional Rust engine (``vlade-rag-core``) with pure-Python fallbacks.

Install the engine with ``pip install "vlade-rag[native]"``. Without it, every function in this
module uses the reference implementation in ``_reference``, which returns the same result
(ADR-0003). The fallback logs one warning at import time.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from types import ModuleType
from typing import Literal

from vlade_rag.native import _reference

logger = logging.getLogger(__name__)

_core: ModuleType | None
try:
    import vlade_rag_core
except ImportError:
    _core = None
    logger.warning(
        "vlade-rag-core is not installed; using pure-Python fallbacks. "
        'Install "vlade-rag[native]" for better performance.'
    )
else:
    _core = vlade_rag_core

NATIVE_AVAILABLE: bool = _core is not None

Backend = Literal["rust", "python"]
STRATEGIES = _reference.STRATEGIES


def backend() -> Backend:
    """Return which implementation backs the functions of this module."""
    return "rust" if _core is not None else "python"


def engine_version() -> str | None:
    """Return the Rust engine version, or ``None`` when the fallback is active."""
    if _core is None:
        return None
    return str(_core.__version__)


def normalize_text(text: str, dehyphenate: bool = True) -> str:
    if _core is not None:
        return str(_core.normalize_text(text, dehyphenate))
    return _reference.normalize_text(text, dehyphenate)


def token_spans(text: str) -> list[tuple[int, int]]:
    if _core is not None:
        return list(_core.token_spans(text))
    return _reference.token_spans(text)


def count_tokens(texts: Sequence[str]) -> list[int]:
    if _core is not None:
        return list(_core.count_tokens(list(texts)))
    return _reference.count_tokens(texts)


def split_text(
    text: str, strategy: str, max_tokens: int, overlap_tokens: int
) -> list[tuple[int, int, int]]:
    if _core is not None:
        return list(_core.split_text(text, strategy, max_tokens, overlap_tokens))
    return _reference.split_text(text, strategy, max_tokens, overlap_tokens)


def content_hash(data: bytes) -> str:
    if _core is not None:
        return str(_core.content_hash(data))
    return _reference.content_hash(data)


def simhash(text: str) -> int:
    if _core is not None:
        return int(_core.simhash(text))
    return _reference.simhash(text)


def rrf_fuse(
    rankings: Sequence[Sequence[str]],
    k: float = 60.0,
    weights: Sequence[float] | None = None,
    top_k: int = 10,
) -> list[tuple[str, float]]:
    if _core is not None:
        return list(
            _core.rrf_fuse(
                [list(r) for r in rankings], k, None if weights is None else list(weights), top_k
            )
        )
    return _reference.rrf_fuse(rankings, k, weights, top_k)


__all__ = [
    "NATIVE_AVAILABLE",
    "STRATEGIES",
    "Backend",
    "backend",
    "content_hash",
    "count_tokens",
    "engine_version",
    "normalize_text",
    "rrf_fuse",
    "simhash",
    "split_text",
    "token_spans",
]
