"""Property test: the Rust engine and the Python reference return the same result (ADR-0003).

Skipped when ``vlade-rag-core`` is not installed. The CI runs it in the ``native=true`` jobs.
The alphabet covers Latin text, digits, punctuation, Markdown and whitespace (see the known limit
in ``vlade_rag.native._reference``).
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vlade_rag.native import _reference

vlade_rag_core = pytest.importorskip("vlade_rag_core")

ALPHABET = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "áàâãéêíóôõúçÁÉÍÓÚÇñü"
    " \t\n\r.,;:!?…-#*_()[]\"'/"
    + "".join(chr(cp) for cp in (0x00A0, 0x00AD, 0x200B, 0xFEFF, 0x0301, 0x00, 0x07))
)
texts = st.text(alphabet=ALPHABET, max_size=600)
SETTINGS = settings(max_examples=300, deadline=None)


@SETTINGS
@given(texts, st.booleans())
def test_normalize_text(text: str, dehyphenate: bool) -> None:
    assert vlade_rag_core.normalize_text(text, dehyphenate) == _reference.normalize_text(
        text, dehyphenate
    )


@SETTINGS
@given(texts)
def test_token_spans(text: str) -> None:
    assert vlade_rag_core.token_spans(text) == _reference.token_spans(text)


@SETTINGS
@given(
    texts,
    st.sampled_from(_reference.STRATEGIES),
    st.integers(min_value=1, max_value=60),
    st.integers(min_value=0, max_value=80),
)
def test_split_text(text: str, strategy: str, max_tokens: int, overlap: int) -> None:
    assert vlade_rag_core.split_text(text, strategy, max_tokens, overlap) == _reference.split_text(
        text, strategy, max_tokens, overlap
    )


@SETTINGS
@given(st.binary(max_size=2048))
def test_content_hash(data: bytes) -> None:
    assert vlade_rag_core.content_hash(data) == _reference.content_hash(data)


@SETTINGS
@given(texts)
def test_simhash(text: str) -> None:
    assert vlade_rag_core.simhash(text) == _reference.simhash(text)


ids = st.text(alphabet="abcdefgh", min_size=1, max_size=3)


@SETTINGS
@given(
    st.lists(st.lists(ids, max_size=30), min_size=1, max_size=4),
    st.floats(min_value=0.5, max_value=200),
    st.integers(min_value=0, max_value=40),
)
def test_rrf_fuse(rankings: list[list[str]], k: float, top_k: int) -> None:
    assert vlade_rag_core.rrf_fuse(rankings, k, None, top_k) == _reference.rrf_fuse(
        rankings, k, None, top_k
    )
