"""MCP tools (docs/MCP_SPEC.md sections 5.2 to 5.9).

Each tool is a ``ToolSpec``: the JSON schemas of the contract, the minimum role, the rate-limit
group and a handler that calls only use cases. The write tools need the tenant flag
``mcp.write_tools_enabled``; the server checks it before it lists or calls them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from mcp_types import Tool, ToolAnnotations

from vlade_rag.core.application import (
    AnswerQuery,
    DeleteDocument,
    Dependencies,
    GetDocument,
    GetIngestionStatus,
    ListKnowledgeBases,
    ReindexKnowledgeBase,
    RunEvaluation,
    Search,
    SubmitIngestion,
)
from vlade_rag.core.domain import (
    InvalidArgument,
    RawDocument,
    Role,
    TenantContext,
)
from vlade_rag.ingestion.sources.download import read_source
from vlade_rag.mcp.policies import Group

Handler = Callable[[Dependencies, TenantContext, Mapping[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    role: Role
    group: Group
    idempotent: bool
    handler: Handler
    read_only: bool = True
    destructive: bool = False

    def to_mcp(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            annotations=ToolAnnotations(
                read_only_hint=self.read_only,
                destructive_hint=self.destructive,
                idempotent_hint=self.idempotent,
                open_world_hint=False,
            ),
        )


def resource_uri(slug: str, document_id: UUID | str) -> str:
    return f"vlade://kb/{slug}/documents/{document_id}"


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise InvalidArgument(f"'{field}' must be a UUID.") from None


# ---------------------------------------------------------------- vlade_list_knowledge_bases


async def _list_knowledge_bases(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    summaries = await ListKnowledgeBases(deps).execute(ctx)
    return {
        "knowledge_bases": [
            {
                "slug": s.knowledge_base.slug,
                "name": s.knowledge_base.name,
                "language": s.knowledge_base.language,
                "document_count": s.document_count,
                "updated_at": _iso(s.knowledge_base.updated_at),
            }
            for s in summaries
        ]
    }


# ---------------------------------------------------------------- vlade_search


async def _search(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    slug = args["knowledge_base"]
    result = await Search(deps).execute(
        ctx,
        knowledge_base=slug,
        text=args["query"],
        top_k=args.get("top_k", 8),
        filters=args.get("filters"),
        rerank=args.get("rerank"),
    )
    return {
        "results": [
            {
                "rank": r.rank,
                "score": r.score,
                "chunk_id": str(r.chunk.id),
                "document_id": str(r.chunk.document_id),
                "document_title": r.chunk.document_title,
                "text": r.chunk.text,
                "page": r.chunk.page,
                "section": r.chunk.section,
                "resource_uri": resource_uri(result.knowledge_base.slug, r.chunk.document_id),
            }
            for r in result.results
        ],
        "trace_id": result.trace_id,
    }


# ---------------------------------------------------------------- vlade_query


async def _query(deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]) -> dict[str, Any]:
    slug = args["knowledge_base"]
    answer = await AnswerQuery(deps).execute(
        ctx,
        knowledge_base=slug,
        question=args["question"],
        top_k=args.get("top_k"),
        filters=args.get("filters"),
        language=args.get("language"),
    )
    return {
        "answer": answer.text,
        "grounded": answer.grounded,
        "citations": [
            {
                "index": c.index,
                "document_id": str(c.document_id),
                "chunk_id": str(c.chunk_id),
                "document_title": c.document_title,
                "page": c.page,
                "resource_uri": resource_uri(slug, c.document_id),
            }
            for c in answer.citations
        ],
        "model": answer.model,
        "prompt_version": answer.prompt_version,
        "usage": {
            "input_tokens": answer.usage.input_tokens,
            "output_tokens": answer.usage.output_tokens,
        },
        "trace_id": answer.trace_id,
    }


# ---------------------------------------------------------------- vlade_get_document


def document_payload(view: Any) -> dict[str, Any]:
    """The ``document`` object of the tool and of the document resource."""
    doc = view.document
    out: dict[str, Any] = {
        "id": str(doc.id),
        "title": doc.title,
        "source_type": doc.source_type,
        "source_uri": doc.source_uri,
        "mime_type": doc.mime_type,
        "version": None if view.version is None else view.version.version,
        "metadata": dict(doc.metadata),
        "created_at": _iso(doc.created_at),
        "updated_at": _iso(doc.updated_at),
    }
    if view.text is not None:
        out["text"] = view.text
        out["truncated"] = view.truncated
    return out


async def _get_document(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    view = await GetDocument(deps).execute(
        ctx,
        knowledge_base=args["knowledge_base"],
        document_id=_uuid(args["document_id"], "document_id"),
        include_text=args.get("include_text", False),
        max_chars=args.get("max_chars", 20_000),
    )
    return {"document": document_payload(view)}


# ---------------------------------------------------------------- vlade_get_ingestion_status


async def _get_ingestion_status(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    job = await GetIngestionStatus(deps).execute(ctx, _uuid(args["job_id"], "job_id"))
    return {
        "job": {
            "id": str(job.id),
            "kind": job.kind.value,
            "status": job.status.value,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "attempt": s.attempt,
                    "error": None if s.error is None else dict(s.error),
                }
                for s in job.steps
            ],
            "result": None if job.result is None else dict(job.result),
            "error": None if job.error is None else dict(job.error),
            "created_at": _iso(job.created_at),
            "started_at": _iso(job.started_at),
            "finished_at": _iso(job.finished_at),
        }
    }


# ---------------------------------------------------------------- vlade_ingest_document


async def _ingest_document(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    metadata = args.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise InvalidArgument("'metadata' must be a JSON object.")
    source_uri: str | None = None
    declared: str | None = None
    if "content_text" in args:
        data = str(args["content_text"]).encode("utf-8")
        source_type = "upload"
    else:
        source_uri = str(args["source_uri"])
        content = await read_source(deps, ctx, source_uri)
        data, declared = content.data, content.mime_type
        source_type = "uri"
    result = await SubmitIngestion(deps).execute(
        ctx,
        knowledge_base=args["knowledge_base"],
        raw=RawDocument(
            filename=args["filename"],
            mime_type=declared or "",
            data=data,
            source_type=source_type,
            source_uri=source_uri,
            metadata=metadata,
        ),
        title=args.get("title"),
        external_id=args.get("external_id"),
    )
    return {
        "job_id": str(result.job.id),
        "document_id": str(result.document.id),
        "status": result.job.status.value,
    }


# ---------------------------------------------------------------- vlade_delete_document


async def _delete_document(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    knowledge_base = args["knowledge_base"]
    document_id = _uuid(args["document_id"], "document_id")
    view = await GetDocument(deps).execute(
        ctx, knowledge_base=knowledge_base, document_id=document_id
    )
    report = await DeleteDocument(deps).execute(
        ctx,
        knowledge_base=knowledge_base,
        document_id=document_id,
        confirm=args.get("confirm", False),
    )
    if not report.executed:
        return {
            "executed": False,
            "action": "delete_document",
            "document_title": view.document.title,
            "will_delete": {
                "versions": report.versions,
                "chunks": report.chunks,
                "embeddings": report.embeddings,
                "stored_objects": report.stored_objects,
            },
        }
    payload: dict[str, Any] = {"executed": True, "action": "delete_document"}
    if report.audit_event_id is not None:
        payload["audit_event_id"] = str(report.audit_event_id)
    return payload


# ---------------------------------------------------------------- vlade_reindex_knowledge_base


async def _reindex_knowledge_base(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    mode = args["mode"]
    model = args.get("embedding_model")
    if mode == "full" and model:
        raise InvalidArgument("'embedding_model' is valid only in the embeddings mode.")
    embeddings = {"model": model} if model else None
    result = await ReindexKnowledgeBase(deps).execute(
        ctx,
        knowledge_base=args["knowledge_base"],
        mode=mode,
        embeddings=embeddings,
        confirm=args.get("confirm", False),
    )
    if not result.executed:
        preview = result.preview
        return {
            "executed": False,
            "action": "reindex_knowledge_base",
            "knowledge_base": preview.knowledge_base,
            "mode": preview.mode,
            "documents": preview.documents,
            "chunks": preview.chunks,
            "estimated_embedding_calls": preview.estimated_embedding_calls,
        }
    assert result.job is not None  # noqa: S101 - executed means a job
    return {
        "executed": True,
        "action": "reindex_knowledge_base",
        "job_id": str(result.job.id),
    }


# ---------------------------------------------------------------- vlade_evaluate


async def _evaluate(
    deps: Dependencies, ctx: TenantContext, args: Mapping[str, Any]
) -> dict[str, Any]:
    result = await RunEvaluation(deps).execute(
        ctx,
        knowledge_base=args["knowledge_base"],
        dataset=args["dataset"],
        metrics=args.get("metrics"),
        k=args.get("k"),
    )
    return {"job_id": str(result.job.id)}


# ---------------------------------------------------------------- schemas

_UUID = {"type": "string", "format": "uuid"}
# Nullable fields use anyOf, not a list in "type": clients that map the schemas to a dialect with
# one "type" (for example the function declarations of Gemini) reject the list.
_NULL = {"type": "null"}
_NULLABLE_STRING = {"anyOf": [{"type": "string"}, _NULL]}
_NULLABLE_INT = {"anyOf": [{"type": "integer"}, _NULL]}
_NULLABLE_TIME = {"anyOf": [{"type": "string", "format": "date-time"}, _NULL]}
_NULLABLE_OBJECT = {"anyOf": [{"type": "object", "additionalProperties": True}, _NULL]}
_OBJECT = {"type": "object", "additionalProperties": True}

_LIST_IN = {"type": "object", "properties": {}, "additionalProperties": False}
_LIST_OUT = {
    "type": "object",
    "required": ["knowledge_bases"],
    "properties": {
        "knowledge_bases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug", "name", "language", "document_count", "updated_at"],
                "properties": {
                    "slug": {"type": "string"},
                    "name": {"type": "string"},
                    "language": {"type": "string"},
                    "document_count": {"type": "integer"},
                    "updated_at": {"type": "string", "format": "date-time"},
                },
            },
        }
    },
}

_SEARCH_IN = {
    "type": "object",
    "required": ["knowledge_base", "query"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string", "description": "Slug da base."},
        "query": {"type": "string", "minLength": 1, "maxLength": 4000},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
        "filters": {
            "type": "object",
            "description": (
                'Filtro por metadados do documento. Formato: {"campo": valor} para igualdade, '
                'ou {"campo": {"in": [valores]}}.'
            ),
            "additionalProperties": True,
        },
        "rerank": {
            "type": "boolean",
            "description": "Sem valor: usa a configuração da base.",
        },
    },
}
_SEARCH_OUT = {
    "type": "object",
    "required": ["results", "trace_id"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rank", "score", "chunk_id", "document_id", "document_title", "text"],
                "properties": {
                    "rank": {"type": "integer"},
                    "score": {"type": "number"},
                    "chunk_id": _UUID,
                    "document_id": _UUID,
                    "document_title": {"type": "string"},
                    "text": {"type": "string"},
                    "page": _NULLABLE_INT,
                    "section": _NULLABLE_STRING,
                    "resource_uri": {
                        "type": "string",
                        "description": "URI do resource do documento.",
                    },
                },
            },
        },
        "trace_id": _NULLABLE_STRING,
    },
}

_QUERY_IN = {
    "type": "object",
    "required": ["knowledge_base", "question"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string"},
        "question": {"type": "string", "minLength": 1, "maxLength": 4000},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        "filters": {"type": "object", "additionalProperties": True},
        "language": {"type": "string", "enum": ["pt-BR", "en"]},
    },
}
_QUERY_OUT = {
    "type": "object",
    "required": ["answer", "grounded", "citations", "trace_id"],
    "properties": {
        "answer": {"type": "string"},
        "grounded": {"type": "boolean"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["index", "document_id", "chunk_id", "document_title"],
                "properties": {
                    "index": {"type": "integer"},
                    "document_id": _UUID,
                    "chunk_id": _UUID,
                    "document_title": {"type": "string"},
                    "page": _NULLABLE_INT,
                    "resource_uri": {"type": "string"},
                },
            },
        },
        "model": {"type": "string"},
        "prompt_version": {"type": "string"},
        "usage": {
            "type": "object",
            "properties": {
                "input_tokens": {"type": "integer"},
                "output_tokens": {"type": "integer"},
            },
        },
        "trace_id": _NULLABLE_STRING,
    },
}

_DOCUMENT_IN = {
    "type": "object",
    "required": ["knowledge_base", "document_id"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string"},
        "document_id": _UUID,
        "include_text": {"type": "boolean", "default": False},
        "max_chars": {"type": "integer", "minimum": 1000, "maximum": 100000, "default": 20000},
    },
}
_DOCUMENT_OUT = {
    "type": "object",
    "required": ["document"],
    "properties": {
        "document": {
            "type": "object",
            "required": ["id", "title", "source_type", "mime_type", "metadata"],
            "properties": {
                "id": _UUID,
                "title": {"type": "string"},
                "source_type": {"type": "string"},
                "source_uri": _NULLABLE_STRING,
                "mime_type": {"type": "string"},
                "version": _NULLABLE_INT,
                "metadata": _OBJECT,
                "created_at": _NULLABLE_TIME,
                "updated_at": _NULLABLE_TIME,
                "text": {"type": "string"},
                "truncated": {"type": "boolean"},
            },
        }
    },
}

_JOB_IN = {
    "type": "object",
    "required": ["job_id"],
    "additionalProperties": False,
    "properties": {"job_id": _UUID},
}
_JOB_OUT = {
    "type": "object",
    "required": ["job"],
    "properties": {
        "job": {
            "type": "object",
            "required": ["id", "kind", "status", "steps"],
            "properties": {
                "id": _UUID,
                "kind": {"type": "string"},
                "status": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "status", "attempt"],
                        "properties": {
                            "name": {"type": "string"},
                            "status": {"type": "string"},
                            "attempt": {"type": "integer"},
                            "error": _NULLABLE_OBJECT,
                        },
                    },
                },
                "result": _NULLABLE_OBJECT,
                "error": _NULLABLE_OBJECT,
                "created_at": _NULLABLE_TIME,
                "started_at": _NULLABLE_TIME,
                "finished_at": _NULLABLE_TIME,
            },
        }
    },
}


_INGEST_IN = {
    "type": "object",
    "required": ["knowledge_base", "filename"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string"},
        "filename": {"type": "string", "maxLength": 255},
        "content_text": {"type": "string", "maxLength": 1000000},
        "source_uri": {"type": "string", "format": "uri"},
        "title": {"type": "string"},
        "external_id": {"type": "string", "maxLength": 255},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "oneOf": [
        {"required": ["content_text"]},
        {"required": ["source_uri"]},
    ],
}
_INGEST_OUT = {
    "type": "object",
    "required": ["job_id", "document_id", "status"],
    "properties": {
        "job_id": _UUID,
        "document_id": _UUID,
        # "succeeded" when the content is equal to the current version (nothing to ingest).
        "status": {"type": "string", "enum": ["pending", "succeeded"]},
    },
}

_DELETE_IN = {
    "type": "object",
    "required": ["knowledge_base", "document_id"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string"},
        "document_id": _UUID,
        "confirm": {"type": "boolean", "default": False},
    },
}
_DELETE_OUT = {
    "type": "object",
    "required": ["executed", "action"],
    "properties": {
        "executed": {"type": "boolean"},
        "action": {"type": "string", "const": "delete_document"},
        "document_title": {"type": "string"},
        "will_delete": {
            "type": "object",
            "required": ["versions", "chunks", "embeddings", "stored_objects"],
            "properties": {
                "versions": {"type": "integer"},
                "chunks": {"type": "integer"},
                "embeddings": {"type": "integer"},
                "stored_objects": {"type": "integer"},
            },
        },
        "audit_event_id": _UUID,
    },
}

_REINDEX_IN = {
    "type": "object",
    "required": ["knowledge_base", "mode"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string"},
        "mode": {"type": "string", "enum": ["embeddings", "full"]},
        "embedding_model": {
            "type": "string",
            "description": (
                "Só no modo embeddings. Sem valor: usa o modelo da configuração atual."
            ),
        },
        "confirm": {"type": "boolean", "default": False},
    },
}
_REINDEX_OUT = {
    "type": "object",
    "required": ["executed", "action"],
    "properties": {
        "executed": {"type": "boolean"},
        "action": {"type": "string", "const": "reindex_knowledge_base"},
        "knowledge_base": {"type": "string"},
        "mode": {"type": "string", "enum": ["embeddings", "full"]},
        "documents": {"type": "integer"},
        "chunks": {"type": "integer"},
        "estimated_embedding_calls": {"type": "integer"},
        "job_id": _UUID,
    },
}


_EVALUATE_IN = {
    "type": "object",
    "required": ["knowledge_base", "dataset"],
    "additionalProperties": False,
    "properties": {
        "knowledge_base": {"type": "string"},
        "dataset": {"type": "string", "description": "Nome do dataset registrado."},
        "metrics": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["recall_at_k", "precision_at_k", "mrr", "ndcg"],
            },
        },
        "k": {"type": "integer", "minimum": 1, "maximum": 50},
    },
}
_EVALUATE_OUT = {
    "type": "object",
    "required": ["job_id"],
    "properties": {"job_id": _UUID},
}


def read_tools() -> list[ToolSpec]:
    """The read tools, in the order of MCP_SPEC section 5.1."""
    return [
        ToolSpec(
            name="vlade_list_knowledge_bases",
            description=(
                "Lista as bases de conhecimento que a sua chave pode ler. Use esta ferramenta "
                "antes de `vlade_search` ou `vlade_query` se você não sabe o `slug` da base."
            ),
            input_schema=_LIST_IN,
            output_schema=_LIST_OUT,
            role=Role.READER,
            group=Group.LIGHT,
            idempotent=True,
            handler=_list_knowledge_bases,
        ),
        ToolSpec(
            name="vlade_search",
            description=(
                "Busca trechos de documentos em uma base de conhecimento. Devolve os trechos com "
                "pontuação e a origem de cada trecho. Use esta ferramenta quando você quer ler as "
                "fontes e escrever a resposta você mesmo. Para receber uma resposta pronta com "
                "citações, use `vlade_query`."
            ),
            input_schema=_SEARCH_IN,
            output_schema=_SEARCH_OUT,
            role=Role.READER,
            group=Group.SEARCH,
            idempotent=True,
            handler=_search,
        ),
        ToolSpec(
            name="vlade_query",
            description=(
                "Faz uma pergunta a uma base de conhecimento e devolve uma resposta gerada só a "
                "partir das fontes, com citações no formato [n]. Se `grounded` é false, as fontes "
                "não têm a resposta. Nesse caso, não complete a resposta com conhecimento próprio "
                "sem avisar o usuário."
            ),
            input_schema=_QUERY_IN,
            output_schema=_QUERY_OUT,
            role=Role.READER,
            group=Group.GENERATION,
            idempotent=False,
            handler=_query,
        ),
        ToolSpec(
            name="vlade_get_document",
            description=(
                "Lê os metadados de um documento e, se você pedir, o texto do documento. O texto "
                "pode vir cortado. Nesse caso, `truncated` é true."
            ),
            input_schema=_DOCUMENT_IN,
            output_schema=_DOCUMENT_OUT,
            role=Role.READER,
            group=Group.LIGHT,
            idempotent=True,
            handler=_get_document,
        ),
        ToolSpec(
            name="vlade_get_ingestion_status",
            description=(
                "Informa o estado de um job de ingestão, de reindexação ou de avaliação. Os "
                "estados finais são succeeded, failed e cancelled."
            ),
            input_schema=_JOB_IN,
            output_schema=_JOB_OUT,
            role=Role.READER,
            group=Group.LIGHT,
            idempotent=True,
            handler=_get_ingestion_status,
        ),
    ]


def write_tools() -> list[ToolSpec]:
    """The write tools, in the order of MCP_SPEC section 5.1."""
    return [
        ToolSpec(
            name="vlade_ingest_document",
            description=(
                "Envia um documento para uma base de conhecimento. A ingestão é assíncrona. A "
                "ferramenta devolve um job_id. Use `vlade_get_ingestion_status` para acompanhar "
                "o job. Envie o texto em `content_text` ou um endereço em `source_uri`. Não envie "
                "os dois."
            ),
            input_schema=_INGEST_IN,
            output_schema=_INGEST_OUT,
            role=Role.WRITER,
            group=Group.WRITE,
            idempotent=False,
            handler=_ingest_document,
            read_only=False,
        ),
        ToolSpec(
            name="vlade_delete_document",
            description=(
                "Apaga um documento, todas as versões, os trechos, os vetores e o arquivo "
                "original. A exclusão não pode ser desfeita. Primeiro chame a ferramenta sem "
                "`confirm` para ver a prévia. Mostre a prévia ao usuário. Chame de novo com "
                "`confirm: true` só depois de o usuário aprovar."
            ),
            input_schema=_DELETE_IN,
            output_schema=_DELETE_OUT,
            role=Role.ADMIN,
            group=Group.ADMIN,
            idempotent=True,
            handler=_delete_document,
            read_only=False,
            destructive=True,
        ),
        ToolSpec(
            name="vlade_reindex_knowledge_base",
            description=(
                "Reindexa uma base de conhecimento. O modo embeddings gera os vetores de novo "
                "com o modelo informado. O modo full processa de novo todos os arquivos "
                "originais. A reindexação consome tempo e custo de provedor. Primeiro chame a "
                "ferramenta sem `confirm` para ver a estimativa. Chame de novo com `confirm: "
                "true` só depois de o usuário aprovar."
            ),
            input_schema=_REINDEX_IN,
            output_schema=_REINDEX_OUT,
            role=Role.ADMIN,
            group=Group.ADMIN,
            idempotent=False,
            handler=_reindex_knowledge_base,
            read_only=False,
            destructive=True,
        ),
        ToolSpec(
            name="vlade_evaluate",
            description=(
                "Inicia uma avaliação de qualidade de uma base com um dataset registrado. A "
                "avaliação é assíncrona e devolve um job_id."
            ),
            input_schema=_EVALUATE_IN,
            output_schema=_EVALUATE_OUT,
            role=Role.ADMIN,
            group=Group.ADMIN,
            idempotent=False,
            handler=_evaluate,
            read_only=False,
        ),
    ]


def all_tools() -> list[ToolSpec]:
    """Every tool. The server filters them by role and by the tenant setting."""
    return [*read_tools(), *write_tools()]
