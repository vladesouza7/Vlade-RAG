"""Pure-Python reference implementation of the native engine.

This module is the specification. ``packages/rust/vlade_rag_core`` implements the same
algorithms, and ``tests/unit/test_native_equivalence.py`` checks that both return the same
result (ADR-0003).

Known limit: word characters use ``str.isalnum`` here and ``char::is_alphanumeric`` in Rust.
Both agree on Latin, Greek and Cyrillic scripts and on digits. They can differ on rare
combining marks of other scripts.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Sequence

# ---------------------------------------------------------------- character classes

# Characters mapped to a plain space: tab, no-break space and the other Zs spaces.
_SPACE_LIKE = frozenset(
    chr(cp) for cp in (0x09, 0x00A0, 0x1680, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000)
)
# Format characters removed during normalization: soft hyphen, zero-width and BOM.
_DROPPED_FORMAT = frozenset(chr(cp) for cp in (0x00AD, *range(0x200B, 0x2010), 0x2060, 0xFEFF))
# Whitespace for tokenization (explicit, so Python and Rust agree).
_WHITESPACE = (
    frozenset(chr(cp) for cp in (0x20, 0x0A, 0x0D, 0x0B, 0x0C, 0x85, 0x2028, 0x2029)) | _SPACE_LIKE
)


def _is_control(c: str) -> bool:
    cp = ord(c)
    return cp < 0x20 or 0x7F <= cp <= 0x9F


def _is_word(c: str) -> bool:
    return c.isalnum()


# ---------------------------------------------------------------- normalization


def normalize_text(text: str, dehyphenate: bool = True) -> str:
    """Normalize extracted text.

    1. Unicode NFC.
    2. ``\\r\\n`` and ``\\r`` become ``\\n``.
    3. Tab and Unicode spaces become a space. Control and format characters are removed.
    4. If ``dehyphenate``: ``word-\\nword`` becomes ``wordword``.
    5. Each line: runs of spaces collapse to one space, and the line is stripped.
    6. Three or more line breaks collapse to two.
    7. Leading and trailing spaces and line breaks are removed.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned: list[str] = []
    for c in text:
        if c == "\n":
            cleaned.append(c)
        elif c in _SPACE_LIKE:
            cleaned.append(" ")
        elif _is_control(c) or c in _DROPPED_FORMAT:
            continue
        else:
            cleaned.append(c)
    if dehyphenate:
        cleaned = _dehyphenate(cleaned)
    lines = "".join(cleaned).split("\n")
    joined = "\n".join(" ".join(part for part in line.split(" ") if part) for line in lines)
    out: list[str] = []
    newlines = 0
    for c in joined:
        if c == "\n":
            newlines += 1
            if newlines <= 2:
                out.append(c)
        else:
            newlines = 0
            out.append(c)
    return "".join(out).strip("\n ")


def _dehyphenate(chars: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(chars)
    while i < n:
        if (
            chars[i] == "-"
            and i > 0
            and i + 2 < n
            and chars[i + 1] == "\n"
            and _is_word(chars[i - 1])
            and _is_word(chars[i + 2])
        ):
            i += 2
            continue
        out.append(chars[i])
        i += 1
    return out


# ---------------------------------------------------------------- tokens


def token_spans(text: str) -> list[tuple[int, int]]:
    """Approximate tokens: runs of word characters, or one other non-space character.

    Offsets are code point indexes, like Python string indexes.
    """
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, c in enumerate(text):
        if _is_word(c):
            if start is None:
                start = i
            continue
        if start is not None:
            spans.append((start, i))
            start = None
        if c not in _WHITESPACE:
            spans.append((i, i + 1))
    if start is not None:
        spans.append((start, len(text)))
    return spans


def count_tokens(texts: Sequence[str]) -> list[int]:
    return [len(token_spans(t)) for t in texts]


# ---------------------------------------------------------------- chunking

_SENTENCE_END = frozenset(".!?…")
_HEADING_SCORE = 5
STRATEGIES = ("tokens", "recursive", "markdown", "sentence")


def _boundary_scores(text: str, spans: list[tuple[int, int]], strategy: str) -> list[int]:
    """``scores[i]`` rates a cut before token ``i`` (higher is a better place to cut)."""
    scores = [0] * len(spans)
    for i in range(1, len(spans)):
        if strategy == "tokens":
            scores[i] = 1
            continue
        gap = text[spans[i - 1][1] : spans[i][0]]
        newlines = gap.count("\n")
        prev = text[spans[i - 1][0] : spans[i - 1][1]]
        sentence_end = prev in _SENTENCE_END and len(gap) > 0
        if strategy == "sentence":
            scores[i] = 2 if (newlines >= 1 or sentence_end) else (1 if gap else 0)
            continue
        if newlines >= 2:
            base = 4
        elif newlines == 1:
            base = 3
        elif sentence_end:
            base = 2
        elif gap:
            base = 1
        else:
            base = 0
        if strategy == "markdown" and newlines >= 1 and text[spans[i][0]] == "#":
            base = _HEADING_SCORE
        scores[i] = base
    return scores


def split_text(
    text: str, strategy: str, max_tokens: int, overlap_tokens: int
) -> list[tuple[int, int, int]]:
    """Split text into chunks of at most ``max_tokens`` approximate tokens.

    Returns ``(start_offset, end_offset, token_count)`` for each chunk. The algorithm cuts at
    the best boundary inside the window ``[start + max_tokens // 4, start + max_tokens]``.
    Ties go to the latest boundary. The next chunk starts ``overlap_tokens`` tokens before
    the cut, except after a Markdown heading cut, where it starts at the heading.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    if max_tokens < 1:
        raise ValueError("max_tokens must be at least 1")
    overlap = max(0, min(overlap_tokens, max_tokens - 1))
    spans = token_spans(text)
    n = len(spans)
    if n == 0:
        return []
    scores = _boundary_scores(text, spans, strategy)
    min_size = max(1, max_tokens // 4)
    chunks: list[tuple[int, int, int]] = []
    s = 0
    while s < n:
        e = min(s + max_tokens, n)
        if e == n:
            cut = n
        else:
            cut = e
            best = -1
            for c in range(s + min_size, e + 1):
                if scores[c] >= best:
                    best = scores[c]
                    cut = c
        chunks.append((spans[s][0], spans[cut - 1][1], cut - s))
        if cut >= n:
            break
        # No overlap across a Markdown heading: the next chunk starts at the heading.
        s = cut if scores[cut] == _HEADING_SCORE else max(cut - overlap, s + 1)
    return chunks


# ---------------------------------------------------------------- hashing

_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK64 = (1 << 64) - 1


def content_hash(data: bytes) -> str:
    """SHA-256 in lowercase hexadecimal."""
    return hashlib.sha256(data).hexdigest()


def _fnv1a64(data: bytes) -> int:
    h = _FNV_OFFSET
    for b in data:
        h ^= b
        h = (h * _FNV_PRIME) & _MASK64
    return h


def simhash(text: str) -> int:
    """64-bit SimHash over lowercase word tokens, with FNV-1a 64 as feature hash."""
    weights = [0] * 64
    found = False
    for start, end in token_spans(text):
        token = text[start:end]
        if not _is_word(token[0]):
            continue
        found = True
        h = _fnv1a64(token.lower().encode("utf-8"))
        for bit in range(64):
            weights[bit] += 1 if (h >> bit) & 1 else -1
    if not found:
        return 0
    value = 0
    for bit in range(64):
        if weights[bit] > 0:
            value |= 1 << bit
    return value


# ---------------------------------------------------------------- fusion


def rrf_fuse(
    rankings: Sequence[Sequence[str]],
    k: float = 60.0,
    weights: Sequence[float] | None = None,
    top_k: int = 10,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: ``score(d) = sum_i w_i / (k + rank_i(d))``, rank from 1.

    A repeated id inside one ranking counts only at its first position. Ties are broken by the
    rank in each list, in list order (missing ranks last), then by id.
    """
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights must have one value per ranking")
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    ranks: dict[str, list[int]] = {}
    missing = 1 << 62
    for i, ranking in enumerate(rankings):
        w = 1.0 if weights is None else float(weights[i])
        seen: set[str] = set()
        for position, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            if item not in scores:
                scores[item] = 0.0
                ranks[item] = [missing] * len(rankings)
            scores[item] += w / (k + position)
            ranks[item][i] = position
    ordered = sorted(scores, key=lambda d: (-scores[d], ranks[d], d))
    return [(d, scores[d]) for d in ordered[: max(0, top_k)]]
