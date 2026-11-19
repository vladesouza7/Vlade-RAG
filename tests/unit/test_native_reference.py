"""Behavior of the native functions. Runs against the active backend (Rust or Python)."""

import hashlib

import pytest

from vlade_rag import native


def test_normalize_text() -> None:
    assert native.normalize_text("  a  b \r\n\r\n\r\n c\t") == "a b\n\nc"
    assert native.normalize_text("infor-\nmação") == "informação"
    assert native.normalize_text("infor-\nmação", dehyphenate=False) == "infor-\nmação"
    assert native.normalize_text("a­b​c﻿") == "abc"
    assert native.normalize_text("ação") == "ação"  # NFC


def test_token_spans_and_count() -> None:
    assert native.token_spans("Olá, mundo!") == [(0, 3), (3, 4), (5, 10), (10, 11)]
    assert native.count_tokens(["a b", "", "x, y."]) == [2, 0, 4]


def test_split_text_respects_limits() -> None:
    text = " ".join(f"w{i}" for i in range(100))
    chunks = native.split_text(text, "tokens", 30, 5)
    assert all(tokens <= 30 for _, _, tokens in chunks)
    assert chunks[0][0] == 0
    assert chunks[-1][1] == len(text)
    # consecutive chunks overlap by 5 tokens
    assert native.count_tokens([text[chunks[1][0] : chunks[0][1]]]) == [5]


def test_split_text_prefers_structure() -> None:
    text = "a b c.\n\nd e f g h"
    assert native.split_text(text, "recursive", 6, 0)[0] == (0, 6, 4)
    md = "intro text here\n# Title\nbody body body body"
    chunks = native.split_text(md, "markdown", 8, 0)
    assert md[chunks[1][0]] == "#"


def test_split_text_errors() -> None:
    with pytest.raises(ValueError):
        native.split_text("a", "unknown", 10, 0)
    assert native.split_text("   ", "tokens", 10, 0) == []


def test_content_hash_is_sha256() -> None:
    assert native.content_hash(b"vlade") == hashlib.sha256(b"vlade").hexdigest()


def test_simhash() -> None:
    assert native.simhash("Olá Mundo") == native.simhash("olá mundo")
    assert native.simhash("...") == 0
    a = native.simhash("o contrato de venda tem prazo de trinta dias")
    b = native.simhash("o contrato de venda tem prazo de trinta dias úteis")
    c = native.simhash("receita de bolo de chocolate com cobertura")
    assert bin(a ^ b).count("1") < bin(a ^ c).count("1")


def test_rrf_fuse() -> None:
    out = native.rrf_fuse([["a", "b"], ["b", "c"]], k=60, top_k=10)
    assert [d for d, _ in out] == ["b", "a", "c"]
    assert out[0][1] == pytest.approx(1 / 62 + 1 / 61)
    weighted = native.rrf_fuse([["a"], ["b"]], k=60, weights=[1.0, 2.0])
    assert [d for d, _ in weighted] == ["b", "a"]
    assert native.rrf_fuse([["a", "a", "b"]], top_k=1) == [("a", pytest.approx(1 / 61))]
    with pytest.raises(ValueError):
        native.rrf_fuse([["a"]], weights=[1.0, 2.0])
