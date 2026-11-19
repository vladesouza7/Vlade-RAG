# vlade-postgres: PostgreSQL 17 with pgvector, pg_trgm and unaccent (ADR-0004, ADR-0005).
# All extensions in this image use the PostgreSQL License.
# The optional BM25 image (vlade-postgres-bm25, with pg_search, AGPL-3.0) arrives in phase 3.
FROM pgvector/pgvector:0.8.7-pg17-trixie

COPY initdb/ /docker-entrypoint-initdb.d/
