-- Queue depth gauge (roadmap 4.6): count pending jobs across tenants.
-- The worker runs outside a tenant context, and RLS hides every tenant row in a plain SELECT.
-- A definer function performs the count, like vlade_claim_job does for the claim.

CREATE FUNCTION vlade_pending_job_count(p_kind text)
RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT count(*) FROM ingestion_jobs WHERE status = 'pending' AND kind = p_kind
$$;

REVOKE ALL ON FUNCTION vlade_pending_job_count(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vlade_pending_job_count(text) TO vlade_app_group;
