"""Bridge to the optional Rust engine (``vlade-rag-core``) with pure-Python fallbacks.

Install the engine with ``pip install "vlade-rag[native]"``. Without it, every function in this
module falls back to a pure-Python reference implementation that returns the same result
(ADR-0003). The fallback logs one warning at import time.
"""

from __future__ import annotations

import logging
from types import ModuleType
from typing import Literal

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


def backend() -> Backend:
    """Return which implementation backs the functions of this module."""
    return "rust" if _core is not None else "python"


def engine_version() -> str | None:
    """Return the Rust engine version, or ``None`` when the fallback is active."""
    if _core is None:
        return None
    return str(_core.__version__)


__all__ = ["NATIVE_AVAILABLE", "Backend", "backend", "engine_version"]
