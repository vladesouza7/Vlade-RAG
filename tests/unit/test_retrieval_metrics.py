"""Recall@K, Precision@K, MRR and NDCG (RF-70): values computed by hand, and properties."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from vlade_rag.evaluation import metrics as m

RANKED = ["a", "b", "c", "d"]
RELEVANT = {"b", "d"}


def test_recall_and_precision_by_hand() -> None:
    assert m.recall_at_k(RANKED, RELEVANT, 1) == 0.0
    assert m.recall_at_k(RANKED, RELEVANT, 2) == 0.5
    assert m.recall_at_k(RANKED, RELEVANT, 4) == 1.0
    assert m.recall_at_k(RANKED, RELEVANT, 10) == 1.0  # a cutoff past the end is fine
    assert m.precision_at_k(RANKED, RELEVANT, 2) == 0.5
    assert m.precision_at_k(RANKED, RELEVANT, 4) == 0.5
    assert m.precision_at_k(RANKED, RELEVANT, 10) == 0.2  # K counts, even past the end


def test_recall_counts_documents_that_were_never_retrieved() -> None:
    assert m.recall_at_k(["a"], {"a", "missing"}, 5) == 0.5


def test_reciprocal_rank_and_first_rank() -> None:
    assert m.reciprocal_rank(RANKED, RELEVANT) == 0.5
    assert m.first_relevant_rank(RANKED, RELEVANT) == 2
    assert m.reciprocal_rank(["x", "y"], RELEVANT) == 0.0
    assert m.first_relevant_rank(["x", "y"], RELEVANT) is None
    assert m.reciprocal_rank(["b"], RELEVANT) == 1.0


def test_ndcg_by_hand() -> None:
    gain_2 = 1 / math.log2(3)  # b at position 2
    gain_4 = 1 / math.log2(5)  # d at position 4
    ideal = 1 / math.log2(2) + 1 / math.log2(3)  # two relevant documents at positions 1 and 2
    assert m.ndcg_at_k(RANKED, RELEVANT, 4) == pytest.approx((gain_2 + gain_4) / ideal)
    assert m.ndcg_at_k(RANKED, RELEVANT, 2) == pytest.approx(gain_2 / ideal)
    assert m.ndcg_at_k(["b", "d"], RELEVANT, 2) == pytest.approx(1.0)  # the best possible ranking
    assert m.ndcg_at_k(["x"], RELEVANT, 3) == 0.0


def test_ndcg_is_not_inflated_by_documents_never_retrieved() -> None:
    # One of two relevant documents is found at rank 1: the best ranking would also hold the other.
    value = m.ndcg_at_k(["a"], {"a", "missing"}, 5)
    assert value == pytest.approx(1.0 / (1.0 + 1 / math.log2(3)))
    assert value < 1.0


def test_no_relevant_document_scores_zero() -> None:
    assert m.recall_at_k(RANKED, set(), 3) == 0.0
    assert m.ndcg_at_k(RANKED, set(), 3) == 0.0
    assert m.precision_at_k(RANKED, set(), 3) == 0.0


@pytest.mark.parametrize("function", [m.recall_at_k, m.precision_at_k, m.ndcg_at_k])
def test_k_must_be_positive(function) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        function(RANKED, RELEVANT, 0)


def test_unique_in_order_and_mean() -> None:
    assert m.unique_in_order(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
    assert m.unique_in_order([]) == []
    assert m.mean([1.0, 0.0, 0.5]) == 0.5
    assert m.mean([]) == 0.0


# ---------------------------------------------------------------- properties

documents = st.lists(st.integers(0, 15), unique=True, max_size=12)
relevants = st.sets(st.integers(0, 15), min_size=1, max_size=6)
cutoffs = st.integers(1, 15)


@given(documents, relevants, cutoffs)
def test_every_metric_is_between_zero_and_one(
    ranked: list[int], relevant: set[int], k: int
) -> None:
    for value in (
        m.recall_at_k(ranked, relevant, k),
        m.precision_at_k(ranked, relevant, k),
        m.ndcg_at_k(ranked, relevant, k),
        m.reciprocal_rank(ranked, relevant),
    ):
        assert 0.0 <= value <= 1.0 + 1e-12


@given(documents, relevants, cutoffs)
def test_recall_never_drops_when_k_grows(ranked: list[int], relevant: set[int], k: int) -> None:
    assert m.recall_at_k(ranked, relevant, k) <= m.recall_at_k(ranked, relevant, k + 1) + 1e-12


@given(documents, relevants, cutoffs)
def test_precision_and_recall_count_the_same_hits(
    ranked: list[int], relevant: set[int], k: int
) -> None:
    hits_from_precision = m.precision_at_k(ranked, relevant, k) * k
    hits_from_recall = m.recall_at_k(ranked, relevant, k) * len(relevant)
    assert hits_from_precision == pytest.approx(hits_from_recall)


@given(relevants, st.lists(st.integers(100, 110), unique=True, max_size=5), cutoffs)
def test_relevant_documents_first_is_a_perfect_ndcg(
    relevant: set[int], noise: list[int], k: int
) -> None:
    ranked = sorted(relevant) + noise
    assert m.ndcg_at_k(ranked, relevant, k) == pytest.approx(1.0)


@given(documents, relevants, cutoffs)
def test_ndcg_prefers_the_relevant_document_higher_up(
    ranked: list[int], relevant: set[int], k: int
) -> None:
    moved = [d for d in ranked if d in relevant] + [d for d in ranked if d not in relevant]
    assert m.ndcg_at_k(moved, relevant, k) >= m.ndcg_at_k(ranked, relevant, k) - 1e-12
