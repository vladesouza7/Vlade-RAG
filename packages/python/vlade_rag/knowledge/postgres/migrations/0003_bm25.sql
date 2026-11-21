-- BM25 retriever with pg_search (ParadeDB), roadmap 3.4, ADR-0005 and ADR-0022.
-- pg_search (AGPL-3.0) exists only in the image vlade-postgres-bm25. This migration runs on every
-- image: it creates no pg_search object. The functions below use dynamic SQL, so they compile
-- without the extension. The index is created the first time a base uses the bm25 retriever.

-- pg_search does not use its index scan when a row-level security policy applies to the query.
-- vlade_bm25_search runs as vlade_definer, which reads chunks without the tenant policy, and puts
-- the tenant of the transaction (app.tenant_id, the same value the policy reads) in the query.
CREATE POLICY definer_read ON chunks FOR SELECT TO vlade_definer USING (true);
GRANT SELECT ON chunks TO vlade_definer;

-- Same semantics as vlade_rag.knowledge.postgres.filters.filter_sql, for a filter given as JSON:
-- {"op": "eq", "key": k, "value": v}, {"op": "in", "key": k, "values": [...]},
-- {"op": "exists", "key": k}, {"op": "and" | "or", "items": [...]}. NULL matches every row.
CREATE FUNCTION vlade_metadata_matches(p_metadata jsonb, p_filter jsonb)
RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path = public, pg_temp AS $$
DECLARE
  item jsonb;
BEGIN
  IF p_filter IS NULL THEN
    RETURN true;
  END IF;
  CASE p_filter->>'op'
    WHEN 'eq' THEN
      RETURN p_metadata @> jsonb_build_object(p_filter->>'key', p_filter->'value');
    WHEN 'in' THEN
      FOR item IN SELECT value FROM jsonb_array_elements(p_filter->'values') LOOP
        IF p_metadata @> jsonb_build_object(p_filter->>'key', item) THEN
          RETURN true;
        END IF;
      END LOOP;
      RETURN false;
    WHEN 'exists' THEN
      RETURN p_metadata ? (p_filter->>'key');
    WHEN 'and' THEN
      FOR item IN SELECT value FROM jsonb_array_elements(p_filter->'items') LOOP
        IF NOT vlade_metadata_matches(p_metadata, item) THEN
          RETURN false;
        END IF;
      END LOOP;
      RETURN true;
    WHEN 'or' THEN
      FOR item IN SELECT value FROM jsonb_array_elements(p_filter->'items') LOOP
        IF vlade_metadata_matches(p_metadata, item) THEN
          RETURN true;
        END IF;
      END LOOP;
      RETURN false;
    ELSE
      RAISE EXCEPTION 'Unsupported metadata filter operation: %', p_filter->>'op'
        USING ERRCODE = 'invalid_parameter_value';
  END CASE;
END $$;

GRANT EXECUTE ON FUNCTION vlade_metadata_matches(jsonb, jsonb) TO vlade_app_group, vlade_definer;

-- Creates the extension (when the image has it) and the BM25 index. Runs as the table owner,
-- like vlade_ensure_trigram_index. One index field per language: text_pt and text_en use the
-- stemmer and the stop words of the language, text_simple only splits and folds the words.
-- tenant_id, knowledge_base_id and is_published are index fields, so the filters run in the index.
CREATE FUNCTION vlade_ensure_bm25_index()
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_search') THEN
    IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_search') THEN
      RAISE EXCEPTION 'The extension pg_search is not installed in this PostgreSQL server.'
        USING ERRCODE = 'feature_not_supported',
              HINT = 'Use the image vlade-postgres-bm25 (deploy/postgres/Dockerfile.bm25).';
    END IF;
    CREATE EXTENSION IF NOT EXISTS pg_search;
  END IF;
  GRANT USAGE ON SCHEMA pdb, paradedb TO vlade_definer;
  EXECUTE $index$
    CREATE INDEX IF NOT EXISTS chunks_bm25_idx ON chunks USING bm25 (
      id,
      (text::pdb.unicode_words('alias=text_pt', 'stemmer=portuguese', 'ascii_folding=true',
                               'stopwords_language=portuguese')),
      (text::pdb.unicode_words('alias=text_en', 'stemmer=english', 'ascii_folding=true',
                               'stopwords_language=english')),
      (text::pdb.unicode_words('alias=text_simple', 'ascii_folding=true')),
      tenant_id, knowledge_base_id, is_published
    )
  $index$;
END $$;

REVOKE ALL ON FUNCTION vlade_ensure_bm25_index() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vlade_ensure_bm25_index() TO vlade_app_group;

-- BM25 search in one knowledge base of the current tenant. The tenant comes from app.tenant_id,
-- which PostgresDatabase.tenant sets in every transaction. Without it, the result is empty.
-- The values go into the query as quoted literals, so pg_search runs the filters in the index.
-- The metadata filter is not an index field: it reads the row of every matching chunk. So it
-- enters the query only when there is a filter (a NULL filter would cost about 10 times more).
CREATE FUNCTION vlade_bm25_search(
  p_knowledge_base uuid, p_query text, p_field text, p_limit int, p_filter jsonb
)
RETURNS TABLE (chunk_id uuid, score real)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_tenant uuid := nullif(current_setting('app.tenant_id', true), '')::uuid;
BEGIN
  IF v_tenant IS NULL OR p_limit IS NULL OR p_limit < 1 THEN
    RETURN;
  END IF;
  IF p_field NOT IN ('text_pt', 'text_en', 'text_simple') THEN
    RAISE EXCEPTION 'Unknown BM25 field: %', p_field USING ERRCODE = 'invalid_parameter_value';
  END IF;
  RETURN QUERY EXECUTE format(
    'SELECT c.id, pdb.score(c.id)::real FROM chunks c '
    'WHERE c.text::pdb.alias(%L) ||| %L AND c.tenant_id = %L AND c.knowledge_base_id = %L '
    'AND c.is_published %s '
    'ORDER BY pdb.score(c.id) DESC, c.id LIMIT %s',
    p_field, p_query, v_tenant, p_knowledge_base,
    CASE WHEN p_filter IS NULL THEN '' ELSE 'AND vlade_metadata_matches(c.metadata, $1)' END,
    p_limit)
  USING p_filter;
END $$;

ALTER FUNCTION vlade_bm25_search(uuid, text, text, int, jsonb) OWNER TO vlade_definer;
REVOKE ALL ON FUNCTION vlade_bm25_search(uuid, text, text, int, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vlade_bm25_search(uuid, text, text, int, jsonb) TO vlade_app_group;
