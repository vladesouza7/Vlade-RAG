"""Knowledge base configuration (docs/ARCHITECTURE.md section 9.2).

Pydantic is allowed in the domain for validation only. It does no I/O.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChunkStrategy = Literal["tokens", "recursive", "markdown", "sentence"]
RetrieverName = Literal["dense", "lexical", "fuzzy", "bm25", "graph"]
GraphMode = Literal["local", "global", "hybrid", "mix", "naive"]
QueryTransform = Literal["none", "rewrite", "multi_query", "hyde"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChunkingConfig(_Frozen):
    strategy: ChunkStrategy = "markdown"
    max_tokens: int = Field(default=512, ge=16, le=8192)
    overlap_tokens: int = Field(default=64, ge=0)
    tokenizer: str = "BAAI/bge-m3"

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> ChunkingConfig:
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        return self


class EmbeddingsConfig(_Frozen):
    provider: str = "ollama"
    model: str = "bge-m3"
    dimension: int = Field(default=1024, ge=1, le=4000)
    batch_size: int = Field(default=32, ge=1, le=2048)


class FusionConfig(_Frozen):
    strategy: Literal["rrf", "weighted"] = "rrf"
    k: float = Field(default=60.0, gt=0)
    weights: dict[str, float] = Field(default_factory=dict)


class RerankConfig(_Frozen):
    enabled: bool = False
    provider: str = "sentence-transformers"
    model: str = "BAAI/bge-reranker-v2-m3"
    candidates: int = Field(default=50, ge=1, le=500)
    top_n: int = Field(default=8, ge=1, le=100)


class RetrievalConfig(_Frozen):
    retrievers: tuple[RetrieverName, ...] = ("dense", "lexical")
    top_k_per_retriever: int = Field(default=50, ge=1, le=1000)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    query_transform: QueryTransform = "none"
    hnsw_ef_search: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def _at_least_one(self) -> RetrievalConfig:
        if not self.retrievers:
            raise ValueError("at least one retriever is required")
        return self


class GenerationConfig(_Frozen):
    provider: str = "ollama"
    model: str = "qwen3:8b"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_context_tokens: int = Field(default=6000, ge=256)
    max_output_tokens: int = Field(default=1024, ge=16)
    prompt: str = "answer_with_citations"
    require_citations: bool = True


class GraphConfig(_Frozen):
    """Knowledge graph of the base (phase 6, ADR-0032). Off by default: extraction is costly.

    The graph uses its own LLM for entity and relation extraction. LightRAG recommends a model
    with at least 32B parameters, 32k context and no "thinking" mode.
    """

    enabled: bool = False
    provider: str = "openrouter"  # LLM provider name of the extraction model
    model: str = ""  # required when enabled
    max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    mode: GraphMode = "hybrid"
    top_k: int = Field(default=40, ge=1, le=200)  # entities and relations per query
    max_chunks_per_document: int = Field(default=2000, ge=1, le=100_000)

    @model_validator(mode="after")
    def _model_when_enabled(self) -> GraphConfig:
        if self.enabled and not self.model.strip():
            raise ValueError("graph.model is required when graph.enabled is true")
        return self


class OrchestrationConfig(_Frozen):
    """Engine of the query flow (docs/ARCHITECTURE.md section 12.1, ADR-0023).

    The two conditional edges exist only in the ``langgraph`` engine. With
    ``rewrite_below_score = None`` and ``max_attempts = 1`` they never run, and the two engines
    give the same answer.
    """

    engine: Literal["pipeline", "langgraph"] = "pipeline"
    # Rewrite the query once when the best result scores below this value and
    # retrieval.query_transform is "none". The score is the one Search returns (RRF or reranker).
    rewrite_below_score: float | None = Field(default=None, ge=0)
    # Retrieval attempts when the answer is not grounded. Each new attempt multiplies top_k.
    max_attempts: int = Field(default=1, ge=1, le=3)
    retry_top_k_factor: int = Field(default=2, ge=2, le=4)


class KnowledgeBaseConfig(_Frozen):
    language: Literal["pt", "en"] = "pt"
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)

    @model_validator(mode="after")
    def _graph_retriever_needs_graph(self) -> KnowledgeBaseConfig:
        if "graph" in self.retrieval.retrievers and not self.graph.enabled:
            raise ValueError("the 'graph' retriever needs graph.enabled = true")
        return self

    def requires_reindex(self, new: KnowledgeBaseConfig) -> Literal["none", "embeddings", "full"]:
        """Return the reindex mode a change from ``self`` to ``new`` requires (section 9.2)."""
        if self.chunking != new.chunking or self.language != new.language:
            return "full"
        if self.embeddings.model_dump(exclude={"batch_size"}) != new.embeddings.model_dump(
            exclude={"batch_size"}
        ):
            return "embeddings"
        return "none"
