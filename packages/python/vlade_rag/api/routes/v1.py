"""REST API v1 (docs/ARCHITECTURE.md section 14.1)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from vlade_rag.api.deps import CtxDep, RuntimeDep
from vlade_rag.api.schemas import (
    AnswerOut,
    AuditEventOut,
    CitationOut,
    DeletionOut,
    DocumentOut,
    IngestOut,
    JobOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    QueryIn,
    SearchHit,
    SearchIn,
    SearchOut,
    TenantUsageOut,
)
from vlade_rag.core.application import (
    AnswerDelta,
    AnswerFinal,
    AnswerQuery,
    CreateKnowledgeBase,
    DeleteDocument,
    GetDocument,
    GetIngestionStatus,
    GetKnowledgeBase,
    GetUsage,
    KnowledgeBaseSummary,
    ListAuditEvents,
    ListKnowledgeBases,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.domain import InvalidArgument, RawDocument, VladeError

router = APIRouter(prefix="/v1")


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseOut])
async def list_knowledge_bases(ctx: CtxDep, rt: RuntimeDep) -> list[KnowledgeBaseOut]:
    return [KnowledgeBaseOut.of(s) for s in await ListKnowledgeBases(rt.deps).execute(ctx)]


@router.post(
    "/knowledge-bases", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate, ctx: CtxDep, rt: RuntimeDep
) -> KnowledgeBaseOut:
    kb = await CreateKnowledgeBase(rt.deps).execute(
        ctx, slug=body.slug, name=body.name, config=body.config
    )
    return KnowledgeBaseOut.of(KnowledgeBaseSummary(kb, 0))


@router.get("/knowledge-bases/{kb}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(kb: str, ctx: CtxDep, rt: RuntimeDep) -> KnowledgeBaseOut:
    return KnowledgeBaseOut.of(await GetKnowledgeBase(rt.deps).execute(ctx, kb))


@router.post(
    "/knowledge-bases/{kb}/documents",
    response_model=IngestOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_document(
    kb: str,
    ctx: CtxDep,
    rt: RuntimeDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    external_id: Annotated[str | None, Form()] = None,
    metadata: Annotated[str | None, Form(description="JSON object")] = None,
) -> IngestOut:
    limit = rt.deps.limits.max_upload_bytes
    data = await file.read(limit + 1)
    try:
        meta: dict[str, Any] = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError as exc:
        raise InvalidArgument("The field 'metadata' must be a JSON object.") from exc
    if not isinstance(meta, dict):
        raise InvalidArgument("The field 'metadata' must be a JSON object.")
    result = await SubmitIngestion(rt.deps).execute(
        ctx,
        knowledge_base=kb,
        raw=RawDocument(
            filename=file.filename or "upload",
            mime_type=file.content_type or "",
            data=data,
            metadata=meta,
        ),
        title=title,
        external_id=external_id,
    )
    return IngestOut(
        job=JobOut.of(result.job), document_id=result.document.id, skipped=result.skipped
    )


@router.get("/knowledge-bases/{kb}/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    kb: str,
    document_id: UUID,
    ctx: CtxDep,
    rt: RuntimeDep,
    include_text: bool = False,
    max_chars: Annotated[int, Query(ge=1000, le=100_000)] = 20_000,
) -> DocumentOut:
    view = await GetDocument(rt.deps).execute(
        ctx,
        knowledge_base=kb,
        document_id=document_id,
        include_text=include_text,
        max_chars=max_chars,
    )
    return DocumentOut.of(view.document, view.version, view.text, view.truncated)


@router.delete("/knowledge-bases/{kb}/documents/{document_id}", response_model=DeletionOut)
async def delete_document(
    kb: str, document_id: UUID, ctx: CtxDep, rt: RuntimeDep, confirm: bool = False
) -> DeletionOut:
    report = await DeleteDocument(rt.deps).execute(
        ctx, knowledge_base=kb, document_id=document_id, confirm=confirm
    )
    return DeletionOut.of(report)


@router.get("/usage", response_model=TenantUsageOut)
async def get_usage(ctx: CtxDep, rt: RuntimeDep) -> TenantUsageOut:
    return TenantUsageOut.of(await GetUsage(rt.deps).execute(ctx))


@router.get("/audit-events", response_model=list[AuditEventOut])
async def list_audit_events(
    ctx: CtxDep,
    rt: RuntimeDep,
    action: str | None = None,
    outcome: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[AuditEventOut]:
    events = await ListAuditEvents(rt.deps).execute(
        ctx, action=action, outcome=outcome, limit=limit
    )
    return [AuditEventOut.of(e) for e in events]


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: UUID, ctx: CtxDep, rt: RuntimeDep) -> JobOut:
    return JobOut.of(await GetIngestionStatus(rt.deps).execute(ctx, job_id))


@router.post("/knowledge-bases/{kb}/search", response_model=SearchOut)
async def search(kb: str, body: SearchIn, ctx: CtxDep, rt: RuntimeDep) -> SearchOut:
    result = await Search(rt.deps).execute(
        ctx,
        knowledge_base=kb,
        text=body.query,
        top_k=body.top_k,
        filters=body.filters,
        rerank=body.rerank,
    )
    return SearchOut(
        results=[SearchHit.of(item, rank) for rank, item in enumerate(result.results, start=1)],
        trace_id=result.trace_id,
    )


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/knowledge-bases/{kb}/query", response_model=AnswerOut)
async def query(kb: str, body: QueryIn, ctx: CtxDep, rt: RuntimeDep) -> Any:
    use_case = AnswerQuery(rt.deps)
    if not body.stream:
        answer = await use_case.execute(
            ctx,
            knowledge_base=kb,
            question=body.question,
            top_k=body.top_k,
            filters=body.filters,
            language=body.language,
        )
        return AnswerOut.of(answer)

    events = use_case.stream(
        ctx,
        knowledge_base=kb,
        question=body.question,
        top_k=body.top_k,
        filters=body.filters,
        language=body.language,
    )
    # Pull the first event before the response starts, so validation errors become HTTP errors.
    first = await anext(events)

    async def body_iter() -> AsyncIterator[str]:
        try:
            event = first
            while True:
                if isinstance(event, AnswerDelta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, AnswerFinal):
                    answer = event.answer
                    if event.replaced:
                        yield _sse("replace", {"text": answer.text})
                    yield _sse(
                        "citations",
                        [CitationOut.of(c).model_dump(mode="json") for c in answer.citations],
                    )
                    out = AnswerOut.of(answer).model_dump(mode="json", exclude={"citations"})
                    yield _sse("done", out)
                event = await anext(events)
        except StopAsyncIteration:
            return
        except VladeError as exc:
            yield _sse("error", {"code": exc.code, "message": exc.message})

    return StreamingResponse(
        body_iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
