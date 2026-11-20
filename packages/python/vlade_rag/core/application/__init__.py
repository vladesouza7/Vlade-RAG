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
from vlade_rag.core.application.deps import Dependencies, Limits, NoopTracer
from vlade_rag.core.application.documents import DeleteDocument, DocumentView, GetDocument
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
from vlade_rag.core.application.request_limits import EnforceRequestLimits
from vlade_rag.core.application.search import Search, SearchResult

__all__ = [
    "AnswerDelta",
    "AnswerEvent",
    "AnswerFinal",
    "AnswerQuery",
    "CreateKnowledgeBase",
    "DeleteDocument",
    "Dependencies",
    "DocumentView",
    "EnforceRequestLimits",
    "GetDocument",
    "GetIngestionStatus",
    "GetKnowledgeBase",
    "GetUsage",
    "KnowledgeBaseSummary",
    "Limits",
    "ListAuditEvents",
    "ListKnowledgeBases",
    "NoopTracer",
    "RunIngestionJob",
    "Search",
    "SearchResult",
    "SubmitIngestion",
    "SubmitResult",
    "UsageView",
    "assemble_context",
    "validate_answer",
]
