#!/bin/sh
# Knowledge graph database for LightRAG (phase 6, ADR-0032). Runs once, on a new data volume.
# The graph lives in its own database and role: LightRAG isolates tenants by a workspace column,
# without the Row-Level Security of the main database.
set -eu
if [ -z "${VLADE_GRAPH_DB_PASSWORD:-}" ]; then
  echo "VLADE_GRAPH_DB_PASSWORD is empty: the knowledge graph database is not created."
  exit 0
fi
psql -v ON_ERROR_STOP=1 -v pw="$VLADE_GRAPH_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE vlade_graph LOGIN PASSWORD :'pw';
CREATE DATABASE vlade_graph OWNER vlade_graph;
\c vlade_graph
CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
