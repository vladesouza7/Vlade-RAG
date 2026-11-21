"""Span attribute names of the AI spans (ADR-0026).

The names follow the OpenInference semantic conventions, which Arize Phoenix reads. They are
plain OpenTelemetry attributes: the core needs no Phoenix package. The text of questions,
answers and chunks goes into a span only with ``Limits.store_query_text`` (the same rule as
the query log), because it may hold personal data.
"""

from __future__ import annotations

from collections.abc import Sequence

from vlade_rag.core.domain import ScoredChunk

SPAN_KIND = "openinference.span.kind"
CHAIN = "CHAIN"
RETRIEVER = "RETRIEVER"
RERANKER = "RERANKER"
LLM = "LLM"

INPUT_VALUE = "input.value"
OUTPUT_VALUE = "output.value"
LLM_MODEL_NAME = "llm.model_name"
LLM_TOKENS_PROMPT = "llm.token_count.prompt"
LLM_TOKENS_COMPLETION = "llm.token_count.completion"
LLM_TOKENS_TOTAL = "llm.token_count.total"
RERANKER_MODEL_NAME = "reranker.model_name"
RERANKER_TOP_K = "reranker.top_k"
RETRIEVAL_DOCUMENTS = "retrieval.documents"

MAX_DOCUMENTS = 20  # documents listed in a retriever span


def documents(results: Sequence[ScoredChunk], with_content: bool) -> dict[str, str | float]:
    """The retrieved chunks as span attributes: id, score and, optionally, the text."""
    attributes: dict[str, str | float] = {}
    for i, item in enumerate(results[:MAX_DOCUMENTS]):
        prefix = f"{RETRIEVAL_DOCUMENTS}.{i}.document"
        attributes[f"{prefix}.id"] = str(item.chunk.id)
        attributes[f"{prefix}.score"] = float(item.score)
        if with_content:
            attributes[f"{prefix}.content"] = item.chunk.text
    return attributes
