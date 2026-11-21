-- Trigram index for the fuzzy retriever (docs/ARCHITECTURE.md section 7.1, ADR-0019).
-- The index costs space and slows writes, so no base pays for it until one uses the fuzzy
-- retriever. The application asks for the index with this function the first time it runs a fuzzy
-- search. The function runs as the owner of the table, like vlade_ensure_space_index.

CREATE FUNCTION vlade_ensure_trigram_index()
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  CREATE INDEX IF NOT EXISTS chunks_trgm_idx ON chunks USING gin (text gin_trgm_ops);
END $$;

REVOKE ALL ON FUNCTION vlade_ensure_trigram_index() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vlade_ensure_trigram_index() TO vlade_app_group;
