# Changelog

Este arquivo registra as mudanças relevantes de cada versão. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). O projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- Especificação mestre (`VLADE-RAG.md`), documentos fundadores e ADRs 0001 a 0015.
- Workspace `uv` com o pacote `vlade-rag` e workspace Cargo com o motor `vlade-rag-core`.
- Esqueleto dos módulos da arquitetura.
- Configuração tipada por variáveis `VLADE_*`.
- Endpoint `GET /health/live`.
- CLI `vlade-rag` com os comandos `version` e `api serve`.
- Ponte com o motor nativo e implementação de reserva em Python.
- CI: ruff, mypy, pytest com cobertura mínima de 85%, clippy, rustfmt, build das distribuições, verificação de licenças, linter de documentação e teste do Compose.
- Docker Compose com o perfil `dev`: API, PostgreSQL 17 com pgvector, Valkey.
- Arquivos de projeto open source: `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, modelos de issue e de pull request.
- Domínio, ports e casos de uso do núcleo: bases de conhecimento, ingestão, documentos, busca e resposta com citações.
- Motor nativo em Rust e implementação de referência em Python: normalização, tokens aproximados, chunking, SHA-256, SimHash e fusão RRF. Testes de propriedade comparam as duas implementações.
- Adapters em memória para testes e protótipos.
- Adapters PostgreSQL com pgvector, busca textual `tsvector` com `unaccent`, fila de jobs, auditoria, chaves de API e Row-Level Security (ADR-0016).
- Provedores Ollama e API compatível com OpenAI (OpenAI e OpenRouter), com streaming e novas tentativas.
- Parsers de texto, Markdown, HTML e, com o extra `docling`, PDF e DOCX.
- API REST v1 com streaming SSE e erros RFC 9457. CLI com os comandos de administração, ingestão, busca e pergunta. Worker de ingestão.
- OpenTelemetry básico e logs JSON.
- Dataset `legal-ptbr` com 100 documentos e 20 perguntas.
- Compose: serviço de migração, worker, Ollama opcional (`--profile ollama`).
- Provedores remotos prontos: OpenRouter, OpenCode Zen e qualquer API compatível com a OpenAI por variável de ambiente.
- `VLADE_DEFAULT_KB_CONFIG`: configuração padrão das bases novas, com mesclagem parcial.
- Cotas por tenant de documentos e de bytes, com `GET /v1/usage`, `vlade-rag usage` e `vlade-rag tenant quota`. Um arquivo acima da cota recebe `quota_exceeded` (HTTP 413).
- Lista e revogação de chaves de API: `vlade-rag key list` e `vlade-rag key revoke`.
- Limite de requisições por chave e por tenant (token bucket) e cota de requisições por dia. Uma chamada acima do limite recebe `rate_limited` (HTTP 429) com `Retry-After`. Configuração: `VLADE_LIMITS__RATE_PER_KEY_PER_MINUTE`, `VLADE_LIMITS__RATE_PER_TENANT_PER_MINUTE` e `vlade-rag tenant quota --requests-per-day`.
- Adapters Valkey (extra `cache`, `redis-py`): cache e limite de requisições compartilhados entre processos, ligados por `VLADE_CACHE__URL`. O Compose já usa o serviço `valkey`. `GET /health/ready` confere o cache.
- Cache de resultados de busca por base e por `kb_epoch`, com validade de 10 minutos.
- Servidor MCP (extra `mcp`, SDK oficial): ferramentas `vlade_list_knowledge_bases`, `vlade_search`, `vlade_query`, `vlade_get_document` e `vlade_get_ingestion_status`, resources `vlade://kb/{slug}` e `vlade://kb/{slug}/documents/{id}` e os prompts `vlade_answer_with_citations` e `vlade_summarize_document`. Transportes `stdio` e Streamable HTTP (`vlade-rag mcp serve`). A chave de API define o tenant e o papel. Cada chamada tem limite por grupo e grava um evento de auditoria com `interface = mcp`. O serviço `mcp` do Compose roda nos perfis `staging` e `prod`.
- Armazenamento de objetos pela API S3 (extra `s3`, `boto3`): `VLADE_OBJECT_STORAGE__BACKEND=s3` com AWS ou qualquer serviço compatível. O `GET /health/ready` confere o bucket. Os três adapters (memória, arquivos e S3) passam no mesmo contrato do port, e todos recusam chaves inseguras. O MinIO deixou de ser o serviço de exemplo (ADR-0017).
- Provedor Gemini pelo endpoint compatível com a API da OpenAI (`GEMINI_API_KEY`). A opção `embedding_dimensions` de cada provedor compatível envia `dimensions` nos embeddings.
- Agent Skill `skills/vlade-rag/` no padrão agentskills.io, com as regras de uso das ferramentas `vlade_*`.
- Teste do servidor MCP com o MCP Inspector em modo CLI (`scripts/mcp_inspector.sh`), no job `MCP server (Inspector)` da CI.
- Leitura da auditoria: `GET /v1/audit-events` e `vlade-rag audit list`. Eventos novos: cota negada, cota alterada, chave emitida e chave revogada.

### Corrigido

- As políticas de RLS tratam `app.tenant_id` vazio como ausência de tenant.
- Os filtros de metadados no PostgreSQL não codificam mais o JSON duas vezes.
