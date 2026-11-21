"""The local reranker with the real model (roadmap 3.1).

Off by default: the model downloads about 2.3 GB and needs about 2.3 GB of memory. To run it:

    uv sync --extra local-models
    VLADE_TEST_LOCAL_RERANKER=1 uv run pytest tests/integration/test_local_reranker_model.py

Set ``VLADE_TEST_LOCAL_RERANKER_MODEL`` to try another cross-encoder.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from vlade_rag.core.domain import Chunk, ScoredChunk
from vlade_rag.reranking.local import SentenceTransformersReranker

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        os.environ.get("VLADE_TEST_LOCAL_RERANKER") != "1",
        reason="VLADE_TEST_LOCAL_RERANKER=1 runs the real model (about 2.3 GB)",
    ),
]

MODEL = os.environ.get("VLADE_TEST_LOCAL_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

TEXTS = {
    "garantia": "A garantia dos equipamentos é de um ano a partir da compra.",
    "prazo": "O prazo de entrega padrão é de cinco dias úteis para todo o país.",
    "pagamento": "Aceitamos boleto, cartão de crédito e Pix, em até doze vezes.",
}


def chunks() -> list[ScoredChunk]:
    tenant, kb, doc, version = uuid4(), uuid4(), uuid4(), uuid4()
    return [
        ScoredChunk(
            Chunk(uuid4(), tenant, kb, doc, version, i, text, 12, 0, len(text)),
            score=1.0,
            rank=i + 1,
            retriever="fusion",
        )
        for i, text in enumerate(TEXTS.values())
    ]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Por quanto tempo vale a garantia do equipamento?", "garantia"),
        ("Quantos dias leva a entrega?", "prazo"),
        ("Posso pagar com Pix?", "pagamento"),
    ],
)
async def test_the_real_model_puts_the_relevant_text_first(question: str, expected: str) -> None:
    pytest.importorskip("sentence_transformers")
    ranker = SentenceTransformersReranker(MODEL)
    out = await ranker.rerank(question, chunks(), 3)
    assert out[0].chunk.text == TEXTS[expected]
    assert out[0].score > out[-1].score
