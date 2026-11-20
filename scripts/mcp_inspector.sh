#!/usr/bin/env bash
# Test the MCP server with the MCP Inspector in CLI mode (docs/MCP_SPEC.md section 12).
#
# The script prepares a tenant with one knowledge base, starts the server over Streamable HTTP and
# calls every tool, resource and prompt with the Inspector. It works offline: the knowledge base
# uses the "hashing" embeddings and the "extractive" generation provider.
#
# Needs PostgreSQL, node, jq and the vlade-rag package with the extras "cli", "postgres", "cache"
# and "mcp". Variables:
#   VLADE_DATABASE__OWNER_URL  owner of the database (required)
#   VLADE_DATABASE__URL        URL of the application role (required; "db upgrade" sets its password)
#   INSPECTOR_VERSION          version of @modelcontextprotocol/inspector (default below)
#   MCP_PORT                   port of the server (default 8765)
#   RAG                        the vlade-rag command (default: uv run --no-sync vlade-rag)
set -euo pipefail

INSPECTOR_VERSION="${INSPECTOR_VERSION:-2.16.0}"
PORT="${MCP_PORT:-8765}"
RAG="${RAG:-uv run --no-sync vlade-rag}"
URL="http://127.0.0.1:${PORT}/mcp"
: "${VLADE_DATABASE__OWNER_URL:?set VLADE_DATABASE__OWNER_URL}"
: "${VLADE_DATABASE__URL:?set VLADE_DATABASE__URL}"

WORK="$(mktemp -d)"
SERVER_PID=""
FAILURES=0
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

export VLADE_SECURITY__API_KEY_PEPPER="${VLADE_SECURITY__API_KEY_PEPPER:-inspector-pepper}"
export VLADE_OBJECT_STORAGE__BACKEND=filesystem
export VLADE_OBJECT_STORAGE__PATH="$WORK/objects"
export VLADE_LOG_LEVEL=WARNING

say() { printf '\n== %s\n' "$*"; }
pass() { printf '   ok   %s\n' "$1"; }
fail() { printf '   FAIL %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

# check NAME JSON JQ-FILTER: pass if the filter is true for the JSON.
check() {
  if jq -e "$3" >/dev/null 2>&1 <<<"$2"; then pass "$1"; else
    fail "$1"
    printf '        filter: %s\n        output: %s\n' "$3" "$(printf '%s' "$2" | head -c 600)"
  fi
}

# --------------------------------------------------------------------------- data

say "Prepare the database, a tenant and a knowledge base"
$RAG db upgrade >/dev/null
TENANT="inspector-$(date +%s)"
$RAG tenant create "$TENANT" >/dev/null
ADMIN_KEY="$($RAG key create --tenant "$TENANT" --roles admin 2>/dev/null)"
READER_KEY="$($RAG key create --tenant "$TENANT" --roles reader 2>/dev/null)"

cat >"$WORK/kb.json" <<'EOF'
{
  "language": "pt",
  "chunking": {"strategy": "markdown", "max_tokens": 60, "overlap_tokens": 5},
  "embeddings": {"provider": "hashing", "model": "hashing-v1", "dimension": 64},
  "generation": {"provider": "extractive", "model": "extractive"}
}
EOF
cat >"$WORK/trocas.md" <<'EOF'
# Política de Trocas

## Prazo

O cliente pode trocar o produto em até sete dias corridos após o recebimento.

## Condições

O produto deve estar sem uso e na embalagem original.
EOF
VLADE_API_KEY="$ADMIN_KEY" $RAG kb create docs --config "$WORK/kb.json" >/dev/null
VLADE_API_KEY="$ADMIN_KEY" $RAG ingest docs "$WORK/trocas.md" --wait >/dev/null
JOB_ID="$(VLADE_API_KEY="$ADMIN_KEY" $RAG audit list --action document.ingest --json | jq -r '.[0].details.job_id')"
[ -n "$JOB_ID" ] && [ "$JOB_ID" != null ] || { echo "no ingestion job found"; exit 1; }

# --------------------------------------------------------------------------- server

say "Start the MCP server on $URL"
$RAG mcp serve --transport http --host 127.0.0.1 --port "$PORT" >"$WORK/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL" || true)" = 401 ] && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$WORK/server.log"; echo "the server stopped"; exit 1; }
  sleep 1
done

# inspect KEY ARGS...: run the Inspector CLI against the server with an API key.
inspect() {
  local key="$1"
  shift
  npx --yes "@modelcontextprotocol/inspector@${INSPECTOR_VERSION}" --cli "$URL" \
    --transport http --header "Authorization: Bearer ${key}" "$@"
}
# call KEY TOOL [--tool-arg k=v ...]: call a tool and print the JSON result (exit 0 even on isError).
call() {
  local key="$1" tool="$2"
  shift 2
  # The Inspector writes a line on stderr for an isError result: keep it out of the log.
  inspect "$key" --method tools/call --tool-name "$tool" "$@" 2>>"$WORK/inspector.err" || true
}

# --------------------------------------------------------------------------- tests

say "tools/list"
OUT="$(inspect "$READER_KEY" --method tools/list)"
check "the 5 read tools, in the order of the spec" "$OUT" \
  '[.tools[].name] == ["vlade_list_knowledge_bases","vlade_search","vlade_query","vlade_get_document","vlade_get_ingestion_status"]'
check "every tool has an input and an output schema" "$OUT" \
  'all(.tools[]; (.inputSchema.type == "object") and (.outputSchema.type == "object"))'
check "every tool is read-only and not destructive" "$OUT" \
  'all(.tools[]; .annotations.readOnlyHint == true and .annotations.destructiveHint == false and .annotations.openWorldHint == false)'

if inspect "$READER_KEY" --method tools/list --strict >/dev/null 2>"$WORK/strict.err"; then
  pass "the tool schemas have no portability error (--strict)"
else
  fail "the tool schemas have a portability error (--strict)"; cat "$WORK/strict.err"
fi
if [ -s "$WORK/strict.err" ]; then sed 's/^/        /' "$WORK/strict.err" | head -40; fi  # warnings

say "vlade_list_knowledge_bases"
OUT="$(call "$READER_KEY" vlade_list_knowledge_bases)"
check "lists the knowledge base" "$OUT" \
  '.isError == false and .structuredContent.knowledge_bases[0].slug == "docs" and .structuredContent.knowledge_bases[0].document_count == 1'
check "structured content equals the text block" "$OUT" \
  '(.content[0].text | fromjson) == .structuredContent'

say "vlade_search"
OUT="$(call "$READER_KEY" vlade_search --tool-arg knowledge_base=docs --tool-arg "query=sete dias corridos" --tool-arg top_k=3)"
check "finds the chunk with its source" "$OUT" \
  '.isError == false and (.structuredContent.results[0].text | test("sete dias")) and (.structuredContent.results[0].resource_uri | startswith("vlade://kb/docs/documents/"))'
DOC_ID="$(jq -r '.structuredContent.results[0].document_id' <<<"$OUT")"

say "vlade_query"
OUT="$(call "$READER_KEY" vlade_query --tool-arg knowledge_base=docs --tool-arg "question=Qual é o prazo de troca?")"
check "answers with citations" "$OUT" \
  '.isError == false and .structuredContent.grounded == true and (.structuredContent.citations | length) > 0'

say "vlade_get_document"
OUT="$(call "$READER_KEY" vlade_get_document --tool-arg knowledge_base=docs --tool-arg "document_id=${DOC_ID}" --tool-arg include_text=true)"
check "returns the metadata and the text" "$OUT" \
  '.isError == false and .structuredContent.document.version == 1 and (.structuredContent.document.text | test("sete dias"))'

say "vlade_get_ingestion_status"
OUT="$(call "$READER_KEY" vlade_get_ingestion_status --tool-arg "job_id=${JOB_ID}")"
check "the ingestion job succeeded" "$OUT" \
  '.isError == false and .structuredContent.job.status == "succeeded" and (.structuredContent.job.steps | last | .name) == "publish"'

say "resources"
OUT="$(inspect "$READER_KEY" --method resources/list)"
check "lists the knowledge base, not the documents" "$OUT" '[.resources[].uri] == ["vlade://kb/docs"]'
OUT="$(inspect "$READER_KEY" --method resources/templates/list)"
check "lists the two templates" "$OUT" \
  '[.resourceTemplates[].uriTemplate] == ["vlade://kb/{slug}","vlade://kb/{slug}/documents/{document_id}"]'
OUT="$(inspect "$READER_KEY" --method resources/read --uri "vlade://kb/docs")"
check "reads the knowledge base" "$OUT" '(.contents[0].text | fromjson | .slug) == "docs"'
OUT="$(inspect "$READER_KEY" --method resources/read --uri "vlade://kb/docs/documents/${DOC_ID}")"
check "reads the document" "$OUT" '(.contents[0].text | fromjson | .document.id) == "'"${DOC_ID}"'"'

say "prompts"
OUT="$(inspect "$READER_KEY" --method prompts/list)"
check "lists the two prompts" "$OUT" \
  '[.prompts[].name] == ["vlade_answer_with_citations","vlade_summarize_document"]'
OUT="$(inspect "$READER_KEY" --method prompts/get --prompt-name vlade_answer_with_citations \
  --prompt-args knowledge_base=docs "question=Qual é o prazo?")"
check "builds the message" "$OUT" '.messages[0].content.text | test("vlade_search")'

say "errors"
# An error result has isError and the JSON error in the text block. It has no structuredContent.
OUT="$(call "$READER_KEY" vlade_search --tool-arg knowledge_base=nao-existe --tool-arg query=x)"
check "unknown knowledge base is not_found" "$OUT" \
  '.isError == true and (has("structuredContent") | not) and (.content[0].text | fromjson | .error.code) == "not_found" and (.content[0].text | fromjson | .error.retryable) == false'
OUT="$(call "$READER_KEY" vlade_search --tool-arg knowledge_base=docs --tool-arg query=x --tool-arg top_k=999)"
check "invalid argument is invalid_argument" "$OUT" \
  '.isError == true and (.content[0].text | fromjson | .error.code) == "invalid_argument"'
if inspect "$READER_KEY" --method resources/read --uri "vlade://kb/nao-existe" >"$WORK/missing.out" 2>&1; then
  fail "a missing resource must fail"
else pass "a missing resource fails"; fi

say "authentication"
if inspect "vrag_nope_nope" --method tools/list >"$WORK/badkey.out" 2>&1; then
  fail "an invalid key must be refused"
else pass "an invalid key is refused"; fi
if [ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL" -H 'Content-Type: application/json' -d '{}')" = 401 ]; then
  pass "a request without a key gets 401"
else fail "a request without a key must get 401"; fi

say "audit and server log"
OUT="$(VLADE_API_KEY="$ADMIN_KEY" $RAG audit list --action mcp.tool_call --limit 100 --json)"
check "every tool call is audited with the mcp interface" "$OUT" \
  '([.[] | select(.outcome == "success")] | length) >= 5'
check "the text of the question is never stored" "$OUT" 'tostring | contains("prazo de troca") | not'
if grep -q "Traceback" "$WORK/server.log"; then
  fail "the server log has a traceback"; cat "$WORK/server.log"
else pass "the server log has no traceback"; fi

echo
if [ "$FAILURES" -ne 0 ]; then
  echo "$FAILURES check(s) failed."
  exit 1
fi
echo "All checks passed."
