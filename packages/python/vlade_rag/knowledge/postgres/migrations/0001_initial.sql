-- Vlade-RAG initial schema (docs/ARCHITECTURE.md section 7, ADR-0012, ADR-0016).
-- Runs as the database owner. The owner must be able to create roles.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ---------------------------------------------------------------- roles
-- vlade_app_group: privileges of the application. The login role from VLADE_DATABASE__URL
--                  becomes a member of this group (see the migration runner).
-- vlade_definer:   owner of the SECURITY DEFINER functions that must cross tenants
--                  (authentication, job claim). It has no login.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vlade_app_group') THEN
    CREATE ROLE vlade_app_group NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vlade_definer') THEN
    CREATE ROLE vlade_definer NOLOGIN;
  END IF;
END $$;

-- ---------------------------------------------------------------- text search
CREATE TEXT SEARCH CONFIGURATION vlade_pt (COPY = portuguese);
ALTER TEXT SEARCH CONFIGURATION vlade_pt
  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, portuguese_stem;

CREATE TEXT SEARCH CONFIGURATION vlade_en (COPY = english);
ALTER TEXT SEARCH CONFIGURATION vlade_en
  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, english_stem;

-- ---------------------------------------------------------------- tables
CREATE TABLE tenants (
  id          uuid PRIMARY KEY,
  slug        text NOT NULL UNIQUE,
  name        text NOT NULL,
  status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  settings    jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE principals (
  id          uuid PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name        text NOT NULL,
  kind        text NOT NULL DEFAULT 'service',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
  id           uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  principal_id uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
  key_prefix   text NOT NULL UNIQUE,
  key_hash     bytea NOT NULL,
  roles        text[] NOT NULL,
  expires_at   timestamptz,
  revoked_at   timestamptz,
  last_used_at timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE embedding_spaces (
  id          uuid PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider    text NOT NULL,
  model       text NOT NULL,
  dimension   int  NOT NULL CHECK (dimension BETWEEN 1 AND 4000),
  distance    text NOT NULL DEFAULT 'cosine' CHECK (distance IN ('cosine', 'dot', 'l2')),
  version     int  NOT NULL,
  status      text NOT NULL DEFAULT 'active' CHECK (status IN ('building', 'active', 'retired')),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_bases (
  id                        uuid PRIMARY KEY,
  tenant_id                 uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  slug                      text NOT NULL,
  name                      text NOT NULL,
  language                  text NOT NULL DEFAULT 'pt',
  config                    jsonb NOT NULL,
  active_embedding_space_id uuid NOT NULL REFERENCES embedding_spaces(id),
  epoch                     bigint NOT NULL DEFAULT 0,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, slug)
);

CREATE TABLE documents (
  id                 uuid PRIMARY KEY,
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  knowledge_base_id  uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  external_id        text,
  source_type        text NOT NULL,
  source_uri         text,
  title              text NOT NULL,
  mime_type          text NOT NULL,
  current_version_id uuid,
  metadata           jsonb NOT NULL DEFAULT '{}',
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (knowledge_base_id, external_id)
);
CREATE INDEX documents_kb_idx ON documents (knowledge_base_id);

CREATE TABLE document_versions (
  id           uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version      int  NOT NULL,
  content_hash text NOT NULL,
  storage_key  text NOT NULL,
  size_bytes   bigint NOT NULL,
  status       text NOT NULL DEFAULT 'indexing'
               CHECK (status IN ('indexing', 'published', 'superseded', 'failed')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  UNIQUE (document_id, version)
);

ALTER TABLE documents
  ADD CONSTRAINT documents_current_version_fk
  FOREIGN KEY (current_version_id) REFERENCES document_versions(id) ON DELETE SET NULL;

CREATE TABLE chunks (
  id                  uuid PRIMARY KEY,
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  knowledge_base_id   uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  document_id         uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  ordinal             int  NOT NULL,
  text                text NOT NULL,
  token_count         int  NOT NULL,
  page                int,
  start_offset        int  NOT NULL,
  end_offset          int  NOT NULL,
  section             text,
  metadata            jsonb NOT NULL DEFAULT '{}',
  tsv                 tsvector NOT NULL,
  is_published        boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chunks_tsv_idx      ON chunks USING gin (tsv);
CREATE INDEX chunks_kb_pub_idx   ON chunks (knowledge_base_id) WHERE is_published;
CREATE INDEX chunks_version_idx  ON chunks (document_version_id);
CREATE INDEX chunks_document_idx ON chunks (document_id);
CREATE INDEX chunks_metadata_idx ON chunks USING gin (metadata jsonb_path_ops);

CREATE TABLE chunk_embeddings (
  chunk_id           uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  embedding_space_id uuid NOT NULL REFERENCES embedding_spaces(id) ON DELETE CASCADE,
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  knowledge_base_id  uuid NOT NULL,
  embedding          vector NOT NULL,
  PRIMARY KEY (chunk_id, embedding_space_id)
);

CREATE TABLE ingestion_jobs (
  id                uuid PRIMARY KEY,
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  knowledge_base_id uuid REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  kind              text NOT NULL,
  status            text NOT NULL
                    CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
  requested_by      uuid,
  input             jsonb NOT NULL,
  result            jsonb,
  error             jsonb,
  attempt           int NOT NULL DEFAULT 0,
  locked_by         text,
  locked_until      timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  started_at        timestamptz,
  finished_at       timestamptz
);
CREATE INDEX ingestion_jobs_queue_idx ON ingestion_jobs (created_at) WHERE status = 'pending';
CREATE INDEX ingestion_jobs_running_idx ON ingestion_jobs (locked_until) WHERE status = 'running';

CREATE TABLE ingestion_steps (
  id          uuid PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  job_id      uuid NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  document_id uuid,
  name        text NOT NULL,
  status      text NOT NULL,
  attempt     int  NOT NULL DEFAULT 1,
  error       jsonb,
  started_at  timestamptz,
  finished_at timestamptz,
  UNIQUE (job_id, name)
);

CREATE TABLE query_logs (
  id                uuid PRIMARY KEY,
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  knowledge_base_id uuid,
  principal_id      uuid,
  interface         text NOT NULL,
  mode              text NOT NULL,
  query_hash        bytea NOT NULL,
  query_text        text,
  result_count      int  NOT NULL,
  grounded          boolean,
  latency_ms        int  NOT NULL,
  trace_id          text,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  principal_id  uuid,
  interface     text NOT NULL,
  action        text NOT NULL,
  resource_type text,
  resource_id   text,
  outcome       text NOT NULL,
  details       jsonb NOT NULL DEFAULT '{}',
  trace_id      text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- row-level security
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['principals', 'api_keys', 'embedding_spaces', 'knowledge_bases',
                           'documents', 'document_versions', 'chunks', 'chunk_embeddings',
                           'ingestion_jobs', 'ingestion_steps', 'query_logs', 'audit_events']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I TO vlade_app_group '
      'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
      'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)', t);
  END LOOP;
END $$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenants TO vlade_app_group
  USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- vlade_definer sees every row of the tables its functions read.
CREATE POLICY definer_all ON api_keys TO vlade_definer USING (true) WITH CHECK (true);
CREATE POLICY definer_all ON tenants TO vlade_definer USING (true) WITH CHECK (true);
CREATE POLICY definer_all ON ingestion_jobs TO vlade_definer USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------- privileges
GRANT USAGE ON SCHEMA public TO vlade_app_group, vlade_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vlade_app_group;
GRANT SELECT, UPDATE ON api_keys TO vlade_definer;
GRANT SELECT ON tenants TO vlade_definer;
GRANT SELECT, UPDATE ON ingestion_jobs TO vlade_definer;

-- ---------------------------------------------------------------- cross-tenant functions

-- Authentication: read a key by its public prefix before a tenant is known.
CREATE FUNCTION vlade_authenticate(p_prefix text)
RETURNS TABLE (tenant_id uuid, principal_id uuid, key_hash bytea, roles text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT k.tenant_id, k.principal_id, k.key_hash, k.roles
  FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
  WHERE k.key_prefix = p_prefix
    AND k.revoked_at IS NULL
    AND (k.expires_at IS NULL OR k.expires_at > now())
    AND t.status = 'active'
$$;

-- Queue: take the oldest pending job of any tenant (FOR UPDATE SKIP LOCKED).
CREATE FUNCTION vlade_claim_job(p_worker text, p_lease_seconds int)
RETURNS SETOF ingestion_jobs
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  UPDATE ingestion_jobs SET
    status = 'running', locked_by = p_worker,
    locked_until = now() + make_interval(secs => p_lease_seconds),
    started_at = now(), attempt = attempt + 1
  WHERE id = (
    SELECT id FROM ingestion_jobs
    WHERE status = 'pending'
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1)
  RETURNING *
$$;

-- Tenant lookup by slug (CLI and administration).
CREATE FUNCTION vlade_tenant_by_slug(p_slug text)
RETURNS TABLE (id uuid, slug text, name text, status text, settings jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT t.id, t.slug, t.name, t.status, t.settings FROM tenants t WHERE t.slug = p_slug
$$;

CREATE FUNCTION vlade_heartbeat_job(p_job uuid, p_worker text, p_lease_seconds int)
RETURNS void
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  UPDATE ingestion_jobs SET locked_until = now() + make_interval(secs => p_lease_seconds)
  WHERE id = p_job AND locked_by = p_worker AND status = 'running'
$$;

CREATE FUNCTION vlade_requeue_expired_jobs(p_max_attempts int)
RETURNS int
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n int;
BEGIN
  UPDATE ingestion_jobs SET
    status = CASE WHEN attempt < p_max_attempts THEN 'pending' ELSE 'failed' END,
    error = '{"code": "lease_expired", "message": "Worker lease expired."}'::jsonb,
    locked_by = NULL, locked_until = NULL,
    finished_at = CASE WHEN attempt < p_max_attempts THEN NULL ELSE now() END
  WHERE status = 'running' AND locked_until < now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

ALTER FUNCTION vlade_authenticate(text) OWNER TO vlade_definer;
ALTER FUNCTION vlade_tenant_by_slug(text) OWNER TO vlade_definer;
ALTER FUNCTION vlade_claim_job(text, int) OWNER TO vlade_definer;
ALTER FUNCTION vlade_heartbeat_job(uuid, text, int) OWNER TO vlade_definer;
ALTER FUNCTION vlade_requeue_expired_jobs(int) OWNER TO vlade_definer;

-- Vector index per embedding space. Owned by the table owner (index creation needs it).
-- Arguments are typed and checked, so the dynamic SQL cannot be injected.
CREATE FUNCTION vlade_ensure_space_index(p_space uuid, p_dimension int, p_distance text)
RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
  v_type text;
  v_ops text;
BEGIN
  IF p_dimension < 1 OR p_dimension > 4000 THEN
    RAISE EXCEPTION 'invalid dimension %', p_dimension;
  END IF;
  v_type := CASE WHEN p_dimension <= 2000 THEN 'vector' ELSE 'halfvec' END;
  v_ops := CASE p_distance
    WHEN 'cosine' THEN v_type || '_cosine_ops'
    WHEN 'l2' THEN v_type || '_l2_ops'
    WHEN 'dot' THEN v_type || '_ip_ops'
    ELSE NULL END;
  IF v_ops IS NULL THEN
    RAISE EXCEPTION 'invalid distance %', p_distance;
  END IF;
  EXECUTE format(
    'CREATE INDEX IF NOT EXISTS %I ON chunk_embeddings USING hnsw ((embedding::%s(%s)) %s) '
    'WHERE embedding_space_id = %L',
    'chunk_emb_' || replace(p_space::text, '-', '') || '_hnsw',
    v_type, p_dimension, v_ops, p_space);
END $$;

REVOKE ALL ON FUNCTION vlade_authenticate(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION vlade_tenant_by_slug(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION vlade_claim_job(text, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION vlade_heartbeat_job(uuid, text, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION vlade_requeue_expired_jobs(int) FROM PUBLIC;
REVOKE ALL ON FUNCTION vlade_ensure_space_index(uuid, int, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vlade_authenticate(text) TO vlade_app_group;
GRANT EXECUTE ON FUNCTION vlade_tenant_by_slug(text) TO vlade_app_group;
GRANT EXECUTE ON FUNCTION vlade_claim_job(text, int) TO vlade_app_group;
GRANT EXECUTE ON FUNCTION vlade_heartbeat_job(uuid, text, int) TO vlade_app_group;
GRANT EXECUTE ON FUNCTION vlade_requeue_expired_jobs(int) TO vlade_app_group;
GRANT EXECUTE ON FUNCTION vlade_ensure_space_index(uuid, int, text) TO vlade_app_group;

-- Tables created by later migrations get the same application privileges.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vlade_app_group;
-- The application must not change the migration history.
REVOKE ALL ON vlade_schema_migrations FROM vlade_app_group;
