-- Runs once, when the data volume is created.
-- Roles, text search configurations and RLS policies arrive with the Alembic migrations (phase 1).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
