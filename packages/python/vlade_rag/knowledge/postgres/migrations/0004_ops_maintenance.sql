-- Operations maintenance (roadmap 4.4, ADR-0027): space cleanup and one active reindex.

ALTER TABLE embedding_spaces ADD COLUMN retired_at timestamptz;
ALTER TABLE document_versions ADD COLUMN superseded_at timestamptz;
CREATE INDEX embedding_spaces_cleanup_idx ON embedding_spaces (status, retired_at, created_at);
CREATE INDEX document_versions_superseded_idx ON document_versions (status, superseded_at);

-- Steps are per document. A full reindex records one step per document, so the old key of
-- (job_id, name) would collapse them.
ALTER TABLE ingestion_steps DROP CONSTRAINT ingestion_steps_job_id_name_key;
CREATE UNIQUE INDEX ingestion_steps_job_name_doc_idx
  ON ingestion_steps (job_id, name, document_id);

-- The old code allowed two reindexes of one base to be queued at the same time. Cancel the
-- duplicates before adding the index, so an upgrade does not fail on an existing database.
WITH ranked AS (
  SELECT id, row_number() OVER (
    PARTITION BY knowledge_base_id ORDER BY created_at, id
  ) AS position
  FROM ingestion_jobs
  WHERE kind = 'reindex' AND status IN ('pending', 'running') AND knowledge_base_id IS NOT NULL
)
UPDATE ingestion_jobs j
SET status = 'cancelled', finished_at = now(), locked_by = NULL, locked_until = NULL
FROM ranked r
WHERE j.id = r.id AND r.position > 1;

-- find_active() and enqueue() are separate transactions. The index closes the window between
-- them, so two reindexes of the same base cannot both be pending or running.
CREATE UNIQUE INDEX ingestion_jobs_one_active_reindex_idx ON ingestion_jobs (knowledge_base_id)
  WHERE kind = 'reindex' AND status IN ('pending', 'running') AND knowledge_base_id IS NOT NULL;

-- The application role does not own the HNSW index of a space. The owner drops it. The tenant
-- check prevents a caller from dropping the index of a space of another tenant.
CREATE FUNCTION vlade_drop_space_index(p_space uuid, p_tenant uuid)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM embedding_spaces WHERE id = p_space AND tenant_id = p_tenant
  ) THEN
    RETURN;
  END IF;
  EXECUTE format('DROP INDEX IF EXISTS %I',
                 'chunk_emb_' || replace(p_space::text, '-', '') || '_hnsw');
END $$;

REVOKE ALL ON FUNCTION vlade_drop_space_index(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vlade_drop_space_index(uuid, uuid) TO vlade_app_group;
