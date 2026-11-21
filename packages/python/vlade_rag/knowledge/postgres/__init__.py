"""PostgreSQL adapters: repository, pgvector, tsvector, jobs, audit, tenants, migrations.

Install with the ``postgres`` extra (asyncpg, pgvector).
"""

from vlade_rag.knowledge.postgres.db import PostgresDatabase
from vlade_rag.knowledge.postgres.indexes import (
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
    "PgVectorIndex",
    "PostgresAuditLog",
    "PostgresDatabase",
    "PostgresJobQueue",
    "PostgresKnowledgeRepository",
    "PostgresTenantDirectory",
    "TrigramLexicalIndex",
    "TsvectorLexicalIndex",
]
