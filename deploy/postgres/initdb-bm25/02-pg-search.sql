-- Runs once, when the data volume is created (image vlade-postgres-bm25 only).
-- pg_search: BM25 index for the bm25 retriever (ADR-0005, ADR-0022). License: AGPL-3.0.
CREATE EXTENSION IF NOT EXISTS pg_search;
