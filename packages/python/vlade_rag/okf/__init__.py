"""Open Knowledge Format v0.2 support (phase 6, task 6.10).

The package parses and writes OKF bundles: markdown files with YAML frontmatter. It needs the
``okf`` extra (PyYAML, MIT). The package imports without the extra; calls that need YAML raise
``OkfUnavailable``.
"""

from __future__ import annotations

from vlade_rag.okf.codec import OkfWikiCodec
from vlade_rag.okf.parser import (
    OkfUnavailable,
    parse_bundle,
    parse_page,
    split_frontmatter,
    validate_bundle,
)
from vlade_rag.okf.writer import append_log_entry, render_index, render_log, render_page

__all__ = [
    "OkfUnavailable",
    "OkfWikiCodec",
    "append_log_entry",
    "parse_bundle",
    "parse_page",
    "render_index",
    "render_log",
    "render_page",
    "split_frontmatter",
    "validate_bundle",
]
