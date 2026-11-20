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
- Leitura da auditoria: `GET /v1/audit-events` e `vlade-rag audit list`. Eventos novos: cota negada, cota alterada, chave emitida e chave revogada.

### Corrigido

- As políticas de RLS tratam `app.tenant_id` vazio como ausência de tenant.
- Os filtros de metadados no PostgreSQL não codificam mais o JSON duas vezes.
