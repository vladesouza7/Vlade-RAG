"""Use cases. Each use case receives ``Dependencies`` and a ``TenantContext`` in execute()."""

from vlade_rag.core.application.admin import GetUsage, ListAuditEvents, UsageView
from vlade_rag.core.application.answer import (
    AnswerDelta,
    AnswerEvent,
    AnswerFinal,
    AnswerQuery,
    assemble_context,
    validate_answer,
)
from vlade_rag.core.application.deps import (
    Dependencies,
    Limits,
    NoopMetrics,
    NoopTracer,
    SourcePolicy,
)
from vlade_rag.core.application.documents import DeleteDocument, DocumentView, GetDocument
from vlade_rag.core.application.evaluation import EvaluationResult, RunEvaluation
from vlade_rag.core.application.graph import (
    GraphReindexResult,
    GraphSearchView,
    ReindexGraph,
    SearchGraph,
)
from vlade_rag.core.application.ingestion import (
    GetIngestionStatus,
    RunIngestionJob,
    SubmitIngestion,
    SubmitResult,
)
from vlade_rag.core.application.knowledge_bases import (
    CreateKnowledgeBase,
    GetKnowledgeBase,
    KnowledgeBaseSummary,
    ListKnowledgeBases,
)
from vlade_rag.core.application.reindex import (
    ReindexKnowledgeBase,
    ReindexPreview,
    ReindexResult,
    ReindexRunner,
)
from vlade_rag.core.application.request_limits import EnforceRequestLimits
from vlade_rag.core.application.search import Search, SearchResult
from vlade_rag.core.application.semantic_cache import SemanticCache, SemanticCacheSettings
from vlade_rag.core.application.sources import SyncResult, SyncSource
from vlade_rag.core.application.wiki import (
    DeleteWikiPage,
    GetWikiPage,
    LintWiki,
    ListWikiPages,
    SynthesizeWikiPage,
    WikiLintReport,
    WikiPageView,
    WriteWikiPage,
)

__all__ = [
    "AnswerDelta",
    "AnswerEvent",
    "AnswerFinal",
    "AnswerQuery",
    "CreateKnowledgeBase",
    "DeleteDocument",
    "DeleteWikiPage",
    "Dependencies",
    "DocumentView",
    "EnforceRequestLimits",
    "EvaluationResult",
    "GetDocument",
    "GetIngestionStatus",
    "GetKnowledgeBase",
    "GetUsage",
    "GetWikiPage",
    "GraphReindexResult",
    "GraphSearchView",
    "KnowledgeBaseSummary",
    "Limits",
    "LintWiki",
    "ListAuditEvents",
    "ListKnowledgeBases",
    "ListWikiPages",
    "NoopMetrics",
    "NoopTracer",
    "ReindexGraph",
    "ReindexKnowledgeBase",
    "ReindexPreview",
    "ReindexResult",
    "ReindexRunner",
    "RunEvaluation",
    "RunIngestionJob",
    "Search",
    "SearchGraph",
    "SearchResult",
    "SemanticCache",
    "SemanticCacheSettings",
    "SourcePolicy",
    "SubmitIngestion",
    "SubmitResult",
    "SyncResult",
    "SyncSource",
    "SynthesizeWikiPage",
    "UsageView",
    "WikiLintReport",
    "WikiPageView",
    "WriteWikiPage",
    "assemble_context",
    "validate_answer",
]
