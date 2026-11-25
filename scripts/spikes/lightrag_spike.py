"""Technical spike for phase 6.0: LightRAG on the project PostgreSQL, without any model.

It checks the six points of the plan:

1. PGTableGraphStorage + PGVectorStorage + PGKVStorage + PGDocStatusStorage work on PostgreSQL 17,
   in a separate database.
2. Chunks cut by Vlade-RAG keep their exact text, so a LightRAG chunk maps back to a Vlade-RAG
   chunk by SHA-256 of the content.
3. Two workspaces in the same database do not see each other.
4. ``adelete_by_doc_id`` removes the entities and relations of the document.
5. ``aquery_data`` returns entities, relations and chunks without an answer from the LLM.
6. No package is installed at run time (``pipmaster.install`` is patched to fail).

The LLM is fake and deterministic: it extracts capitalized words as entities and links
consecutive entities. The embedding is feature hashing. Nothing is sent to a model.

Usage (isolated venv with lightrag-hku, asyncpg, pgvector):
    LIGHTRAG_SPIKE_DSN=postgresql://user:pass@127.0.0.1:55432/vlade_graph \\
    python scripts/spikes/lightrag_spike.py
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import math
import os
import re
import sys
import tempfile
from urllib.parse import urlsplit

import numpy as np
import pipmaster

INSTALLS: list[str] = []


def _no_install(*args: object, **kwargs: object) -> None:
    INSTALLS.append(repr(args))
    raise RuntimeError(f"pipmaster.install called at run time: {args!r}")


pipmaster.install = _no_install  # check 6: must never run

DSN = os.environ["LIGHTRAG_SPIKE_DSN"]
_parts = urlsplit(DSN)
os.environ.update(
    {
        "POSTGRES_HOST": _parts.hostname or "127.0.0.1",
        "POSTGRES_PORT": str(_parts.port or 5432),
        "POSTGRES_USER": _parts.username or "",
        "POSTGRES_PASSWORD": _parts.password or "",
        "POSTGRES_DATABASE": _parts.path.lstrip("/"),
    }
)

from lightrag import LightRAG, QueryParam  # noqa: E402
from lightrag.utils import EmbeddingFunc  # noqa: E402

TUPLE = "<|#|>"
COMPLETE = "<|COMPLETE|>"
_NAME = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+(?:\s[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ]+)*")
_STOP = {"O", "A", "Os", "As", "Na", "No", "Em", "Para", "Segundo", "Ele", "Ela"}


async def fake_llm(prompt: str, system_prompt: str | None = None, **kwargs: object) -> str:
    text = f"{system_prompt or ''}\n{prompt}"
    if "---Input Text---" in text or "entity_name" in text or "Entity Types" in text:
        body = text.split("---Input Text---")[-1]
        names = []
        for match in _NAME.finditer(body):
            name = match.group(0).strip()
            if name not in _STOP and name not in names and len(name) > 2:
                names.append(name)
        names = names[:8]
        lines = [f"entity{TUPLE}{n}{TUPLE}concept{TUPLE}{n} aparece no texto." for n in names]
        lines += [
            f"relation{TUPLE}{a}{TUPLE}{b}{TUPLE}relacionado{TUPLE}{a} se relaciona com {b}."
            for a, b in itertools.pairwise(names)
        ]
        return "\n".join(lines) + f"\n{COMPLETE}"
    return "Resumo."


def _embed_one(text: str, dim: int = 64) -> list[float]:
    vector = [0.0] * dim
    for word in re.findall(r"\w+", text.lower()):
        h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
        vector[h % dim] += 1.0 if h >> 63 else -1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


async def fake_embed(texts: list[str], **kwargs: object) -> np.ndarray:
    return np.array([_embed_one(t) for t in texts], dtype=np.float32)


def make(workspace: str, working_dir: str) -> LightRAG:
    return LightRAG(
        working_dir=working_dir,
        workspace=workspace,
        kv_storage="PGKVStorage",
        vector_storage="PGVectorStorage",
        graph_storage="PGTableGraphStorage",
        doc_status_storage="PGDocStatusStorage",
        llm_model_func=fake_llm,
        embedding_func=EmbeddingFunc(embedding_dim=64, max_token_size=8192, func=fake_embed),
    )


CHUNKS_A = [
    "Wayne Grudem defende a Teologia da Aliança na Teologia Sistemática.",
    "Charles Ryrie defende o Dispensacionalismo e distingue Israel e Igreja.",
]
CHUNKS_B = ["Augustus Strong escreveu sobre Batismo de Crentes e Eclesiologia Batista."]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def main() -> int:
    results: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as tmp:
        rag_a = make("t1_kb1", tmp)
        rag_b = make("t2_kb1", tmp)
        await rag_a.initialize_storages()
        await rag_b.initialize_storages()
        results["1 storages initialize on PostgreSQL"] = True

        await rag_a.ainsert_custom_chunks("\n\n".join(CHUNKS_A), CHUNKS_A, doc_id="version-a1")
        await rag_b.ainsert_custom_chunks("\n\n".join(CHUNKS_B), CHUNKS_B, doc_id="version-b1")

        param = QueryParam(
            mode="hybrid",
            top_k=10,
            chunk_top_k=10,
            enable_rerank=False,
            hl_keywords=["Teologia da Aliança", "Dispensacionalismo"],
            ll_keywords=["Wayne Grudem", "Charles Ryrie"],
        )
        data_a = await rag_a.aquery_data("Grudem e Ryrie", param)
        payload = data_a.get("data", {})
        entities = [e["entity_name"] for e in payload.get("entities", [])]
        chunks = [c["content"] for c in payload.get("chunks", [])]
        print("A entities:", entities)
        print("A chunks:", chunks)
        results["5 aquery_data returns entities, relations and chunks"] = bool(
            entities and payload.get("relationships") and chunks
        )
        known = {sha(c) for c in CHUNKS_A}
        results["2 chunk text is unchanged (maps by SHA-256)"] = bool(chunks) and all(
            sha(c) in known for c in chunks
        )

        data_b = await rag_b.aquery_data("Grudem e Ryrie", param)
        b_payload = data_b.get("data", {})
        leaked = [
            e["entity_name"]
            for e in b_payload.get("entities", [])
            if "Grudem" in e["entity_name"] or "Ryrie" in e["entity_name"]
        ] + [c["content"] for c in b_payload.get("chunks", []) if sha(c["content"]) in known]
        print("B sees from A:", leaked)
        results["3 workspaces are isolated"] = not leaked

        deletion = await rag_a.adelete_by_doc_id("version-a1")
        print("delete:", getattr(deletion, "status", deletion))
        after = (await rag_a.aquery_data("Grudem e Ryrie", param)).get("data", {})
        removed = not after.get("entities") and not after.get("chunks")
        results["4 delete removes entities and chunks"] = removed
        still_b = (
            await rag_b.aquery_data(
                "Strong batismo",
                QueryParam(
                    mode="hybrid",
                    enable_rerank=False,
                    hl_keywords=["Batismo de Crentes"],
                    ll_keywords=["Augustus Strong"],
                ),
            )
        ).get("data", {})
        results["3b other workspace untouched by delete"] = bool(still_b.get("entities"))

        await rag_a.finalize_storages()
        await rag_b.finalize_storages()
    results["6 no pip install at run time"] = not INSTALLS

    print()
    for name, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
