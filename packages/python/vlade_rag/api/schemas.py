"""Request and response models of the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vlade_rag.core.application import KnowledgeBaseSummary, UsageView
from vlade_rag.core.domain import (
    Answer,
    AuditEvent,
    Citation,
    DeletionReport,
    Document,
    DocumentVersion,
    IngestionJob,
    KnowledgeBaseConfig,
    ScoredChunk,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeBaseCreate(_Model):
    slug: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] | None = Field(
        default=None, description="Partial configuration, merged over the server default."
    )


class KnowledgeBaseOut(_Model):
    id: UUID
    slug: str
    name: str
    language: str
    document_count: int
    config: KnowledgeBaseConfig

    @classmethod
    def of(cls, summary: KnowledgeBaseSummary) -> KnowledgeBaseOut:
        kb = summary.knowledge_base
        return cls(
            id=kb.id,
            slug=kb.slug,
            name=kb.name,
            language=kb.language,
            document_count=summary.document_count,
            config=kb.config,
        )


class StepOut(_Model):
    name: str
    status: str
    attempt: int
    error: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobOut(_Model):
    id: UUID
    kind: str
    status: str
    knowledge_base_id: UUID | None
    input: dict[str, Any]
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    attempt: int
    steps: list[StepOut]
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, job: IngestionJob) -> JobOut:
        return cls(
            id=job.id,
            kind=job.kind.value,
            status=job.status.value,
            knowledge_base_id=job.knowledge_base_id,
            input=dict(job.input),
            result=None if job.result is None else dict(job.result),
            error=None if job.error is None else dict(job.error),
            attempt=job.attempt,
            steps=[
                StepOut(
                    name=s.name,
                    status=s.status.value,
                    attempt=s.attempt,
                    error=None if s.error is None else dict(s.error),
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                )
                for s in job.steps
            ],
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class IngestOut(_Model):
    job: JobOut
    document_id: UUID
    skipped: bool


class DocumentOut(_Model):
    id: UUID
    title: str
    mime_type: str
    source_type: str
    source_uri: str | None
    external_id: str | None
    metadata: dict[str, Any]
    version: int | None
    status: str | None
    created_at: datetime | None
    updated_at: datetime | None
    text: str | None = None
    truncated: bool = False

    @classmethod
    def of(
        cls,
        doc: Document,
        version: DocumentVersion | None,
        text: str | None = None,
        truncated: bool = False,
    ) -> DocumentOut:
        return cls(
            id=doc.id,
            title=doc.title,
            mime_type=doc.mime_type,
            source_type=doc.source_type,
            source_uri=doc.source_uri,
            external_id=doc.external_id,
            metadata=dict(doc.metadata),
            version=None if version is None else version.version,
            status=None if version is None else version.status.value,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            text=text,
            truncated=truncated,
        )


class DeletionOut(_Model):
    executed: bool
    document_id: UUID
    will_delete: dict[str, int]

    @classmethod
    def of(cls, report: DeletionReport) -> DeletionOut:
        return cls(
            executed=report.executed,
            document_id=report.document_id,
            will_delete={
                "versions": report.versions,
                "chunks": report.chunks,
                "embeddings": report.embeddings,
                "stored_objects": report.stored_objects,
            },
        )


class SearchIn(_Model):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1)
    filters: dict[str, Any] | None = None
    rerank: bool | None = None


class SearchHit(_Model):
    rank: int
    score: float
    chunk_id: UUID
    document_id: UUID
    document_title: str
    text: str
    page: int | None
    section: str | None
    metadata: dict[str, Any]

    @classmethod
    def of(cls, item: ScoredChunk, rank: int) -> SearchHit:
        c = item.chunk
        return cls(
            rank=rank,
            score=item.score,
            chunk_id=c.id,
            document_id=c.document_id,
            document_title=c.document_title,
            text=c.text,
            page=c.page,
            section=c.section,
            metadata=dict(c.metadata),
        )


class SearchOut(_Model):
    results: list[SearchHit]
    trace_id: str | None


class QueryIn(_Model):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1)
    filters: dict[str, Any] | None = None
    language: Literal["pt", "pt-BR", "en"] | None = None
    stream: bool = False


class CitationOut(_Model):
    index: int
    document_id: UUID
    chunk_id: UUID
    document_title: str
    page: int | None
    start_offset: int
    end_offset: int

    @classmethod
    def of(cls, c: Citation) -> CitationOut:
        return cls(
            index=c.index,
            document_id=c.document_id,
            chunk_id=c.chunk_id,
            document_title=c.document_title,
            page=c.page,
            start_offset=c.start_offset,
            end_offset=c.end_offset,
        )


class UsageOut(_Model):
    input_tokens: int
    output_tokens: int


class AnswerOut(_Model):
    answer: str
    grounded: bool
    citations: list[CitationOut]
    model: str
    prompt_name: str
    prompt_version: str
    usage: UsageOut
    trace_id: str | None

    @classmethod
    def of(cls, a: Answer) -> AnswerOut:
        return cls(
            answer=a.text,
            grounded=a.grounded,
            citations=[CitationOut.of(c) for c in a.citations],
            model=a.model,
            prompt_name=a.prompt_name,
            prompt_version=a.prompt_version,
            usage=UsageOut(input_tokens=a.usage.input_tokens, output_tokens=a.usage.output_tokens),
            trace_id=a.trace_id,
        )


class Problem(_Model):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    code: str
    retryable: bool = False


class QuotasOut(_Model):
    documents: int | None
    bytes: int | None
    requests_per_day: int | None


class TenantUsageOut(_Model):
    documents: int
    bytes: int
    requests_today: int
    quotas: QuotasOut

    @classmethod
    def of(cls, view: UsageView) -> TenantUsageOut:
        return cls(
            documents=view.usage.documents,
            bytes=view.usage.bytes,
            requests_today=view.usage.requests_today,
            quotas=QuotasOut(
                documents=view.quotas.documents,
                bytes=view.quotas.bytes,
                requests_per_day=view.quotas.requests_per_day,
            ),
        )


class AuditEventOut(_Model):
    action: str
    outcome: str
    interface: str
    principal_id: UUID | None
    resource_type: str | None
    resource_id: str | None
    details: dict[str, Any]
    trace_id: str | None
    created_at: datetime | None

    @classmethod
    def of(cls, event: AuditEvent) -> AuditEventOut:
        return cls(
            action=event.action,
            outcome=event.outcome,
            interface=event.interface,
            principal_id=event.principal_id,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=dict(event.details),
            trace_id=event.trace_id,
            created_at=event.created_at,
        )
