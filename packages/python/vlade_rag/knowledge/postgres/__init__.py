"""PostgreSQL adapters: repository, pgvector, tsvector, trigram, BM25, jobs, audit, tenants.

Install with the ``postgres`` extra (asyncpg, pgvector).
"""

from vlade_rag.knowledge.postgres.db import PostgresDatabase
from vlade_rag.knowledge.postgres.indexes import (
    PgSearchLexicalIndex,
    PgVectorIndex,
    TrigramLexicalIndex,
    TsvectorLexicalIndex,
)
from vlade_rag.knowledge.postgres.operations import (
    PostgresAuditLog,
    PostgresJobQueue,
    PostgresTenantDirectory,
)
from vlade_rag.knowledge.postgres.repository import PostgresKnowledgeRepository

__all__ = [
    "PgSearchLexicalIndex",
    "PgVectorIndex",
    "PostgresAuditLog",
    "PostgresDatabase",
    "PostgresJobQueue",
    "PostgresKnowledgeRepository",
    "PostgresTenantDirectory",
    "TrigramLexicalIndex",
    "TsvectorLexicalIndex",
]
