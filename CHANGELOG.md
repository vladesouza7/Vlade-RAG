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

### Corrigido

- O `build_runtime` recebia o tracer e não o passava aos casos de uso. Só o span HTTP da API chegava ao coletor de traces.
- As políticas de RLS tratam `app.tenant_id` vazio como ausência de tenant.
- Os filtros de metadados no PostgreSQL não codificam mais o JSON duas vezes.

## [0.4.0] - 2026-11-23

### Adicionado

- Flows Kestra da tarefa 4.1 em `deploy/kestra/flows/`: `ingest_batch`, `reindex_knowledge_base`, `evaluate_nightly` e `backup`. Novo caso de uso `RunEvaluation`, endpoint `POST /v1/evaluations`, job `evaluation`, ferramenta MCP `vlade_evaluate` e registro de datasets por nome em `VLADE_EVALUATION__DATASETS_PATH`. As métricas de resposta com juiz pago continuam só na CLI
- Relatório de consumo de memória do perfil `dev` em `evals/reports/fase4-memoria/`: pico de 166 MiB com 550 buscas concorrentes, abaixo do limite de 3 GB (RNF-11).
- Ferramentas MCP de escrita com confirmação: `vlade_ingest_document`, `vlade_delete_document` e `vlade_reindex_knowledge_base` (fase 4, tarefa 4.3). Elas ficam fora de `tools/list` até `vlade-rag tenant mcp-write <slug> --enable`. A chamada sem `confirm` devolve só a prévia, com resultado de auditoria `preview`. O `source_uri` aceita `s3://` no bucket do tenant e `https://` com `VLADE_SOURCES__ALLOWED_DOMAINS`, sem redirecionamento e com bloqueio de endereços privados. A ferramenta `vlade_evaluate` entrou com a tarefa 4.1
- Reindexação sem parada (ADR-0027): `POST /v1/knowledge-bases/{kb}/reindex` e `vlade-rag reindex`, nos modos `embeddings` (modelo novo, espaço novo e troca atômica) e `full` (chunking novo, uma versão nova por documento). Sem `confirm`, a resposta é uma prévia. As buscas continuam durante a reindexação e nunca misturam espaços de embeddings.
- Módulo `ops` (tarefa 4.4): `vlade-rag ops cleanup` apaga espaços `retired` e `building` órfãos e versões `superseded` depois do período de espera. `vlade-rag ops recover-jobs` devolve jobs vencidos para a fila. `vlade-rag ops health` mostra as verificações de prontidão.
- Guia de implantação (tarefa 4.7): `docs/operacao/implantacao.md` descreve pré-requisitos, variáveis de ambiente, perfis, instalação, verificação, configuração inicial, observabilidade, operação diária, atualização, backup e segurança. A CI passou a verificar a pasta com o linter ASD-STE100.
- Catálogo de métricas da aplicação (tarefa 4.6): port `Metrics` no núcleo, adaptador OpenTelemetry e instrumentação de consultas, busca, geração de LLM, ingestão, fila e avaliação. O Prometheus recebe as métricas pelo Alloy. `tenant_id` não entra nos rótulos.
- Cinco dashboards provisionados no Grafana (tarefa 4.6): `rag-performance`, `llm-observability`, `retrieval-analytics`, `infrastructure` e `workflow-monitoring`. Oito alertas em `deploy/observability/prometheus/rules/alerts.yml`, cada um com um teste de falha provocada em `tests/promtool/alerts.test.yml`, executado pela CI. O script `scripts/observability/seed_telemetry.py` gera dados reais sem provedor externo.
- Pilha de observabilidade (tarefa 4.5, ADR-0015): Alloy, Prometheus, Loki, Tempo e Grafana no perfil `prod`, e o Alloy também no perfil `staging` para enviar aos backends externos. O Alloy recebe OTLP em `4317` e `4318`, escreve métricas no Prometheus, envia traces ao Tempo e lê os logs do Docker para o Loki. O Prometheus coleta Alloy, `node-exporter`, `cadvisor`, `postgres-exporter` e `redis-exporter`. O Grafana provisiona as fontes de dados, com o Tempo ligado aos logs do Loki. Todas as portas escutam em `127.0.0.1`. A configuração e o README estão em `deploy/observability/`.

### Corrigido

- A migração 0005 cria `vlade_pending_job_count`, uma função `SECURITY DEFINER` que conta os jobs pendentes. Antes, a RLS escondia as linhas e o gauge da fila ficava em zero.
