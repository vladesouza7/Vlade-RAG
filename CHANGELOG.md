# Changelog

Este arquivo registra as mudanças relevantes de cada versão. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). O projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- OKF v0.2 e LLM-Wiki (fase 6, tarefas 6.10 e 6.12, ADR-0033): módulo `vlade_rag.okf` no extra `okf` (PyYAML), com parser, escritor e verificação de conformidade. O parser de Markdown guarda o frontmatter OKF nos metadados do documento. Novo port `WikiStore`, com adapters de sistema de arquivos e memória. Casos de uso de leitura, escrita, exclusão, geração e lint de páginas. Rotas `GET` e `POST /v1/knowledge-bases/{kb}/wiki/pages`, `POST /v1/knowledge-bases/{kb}/wiki/lint` e `POST /v1/knowledge-bases/{kb}/wiki/synthesize`. Ferramentas MCP `vlade_wiki_read`, `vlade_wiki_lint`, `vlade_wiki_write` e `vlade_wiki_synthesize` (contrato MCP 1.2.0). A wiki fica desligada por padrão, com `VLADE_WIKI__ENABLED` e `VLADE_WIKI__ROOT`.
- Grafo de conhecimento com LightRAG (fase 6, tarefas 6.0 a 6.7, ADR-0032): port `GraphIndex`, adapter `LightRAGGraphIndex` no extra `graph` e adapter em memória para testes. O grafo fica numa base PostgreSQL separada (`vlade_graph`) e fica desligado por padrão em cada base. A ingestão enfileira o job `graph_index` depois da publicação. O retriever `graph` entra na fusão RRF. Novas rotas `POST /v1/knowledge-bases/{kb}/graph/search` e `POST /v1/knowledge-bases/{kb}/graph/reindex`. Nova ferramenta MCP `vlade_search_graph` (contrato MCP 1.1.0). A Agent Skill ensina a ferramenta nova.
- Site de documentação (fase 5, tarefa 5.7, 2026-11-24): MkDocs com o tema Material, fonte na pasta `docs/` e página inicial em `docs/index.md`. A CI compila com `mkdocs build --strict` e guarda o resultado como artefato. O extra `docs` instala MkDocs Material.
- OIDC/OAuth 2.1 na API e no MCP (fase 5, tarefa 5.5, ADR-0031): `authenticate_bearer` aceita chave de API ou token JWT verificado pelo emissor e JWKS configurados. Os claims viram `TenantContext`, sem mudar os casos de uso. O extra `oidc` traz PyJWT com cryptography.
- Cache semântico de consultas (fase 5, tarefa 5.4, ADR-0030): camada opt-in sobre o port `Cache`, com chave por base e época, limiar de similaridade por cosine e limite de entradas. Funciona em busca densa sem filtros e sem transformação.
- Endpoint `POST /v1/knowledge-bases/{kb}/sources/{source}/sync` e flow Kestra `sync_source` (fase 5, tarefa 5.3, ADR-0029). O endpoint chama o caso de uso `SyncSource`. O flow tem gatilho diário desligado e aceita `source`, `knowledge_base`, `cursor` e `limit`.
- Conectores de origem (fase 5, tarefa 5.2, ADR-0029): `WebSource`, `GoogleDriveSource` e `SqlSource` implementam `DocumentSource`. O caso de uso `SyncSource` lista os itens e envia cada um à ingestão, sem duplicar documentos. O conector de sites reusa a política segura da ADR-0028. O extra `sql` traz SQLAlchemy e aiosqlite.
- Adapter Qdrant de `VectorIndex` (fase 5, tarefa 5.1, ADR-0004) no extra `qdrant`. O pgvector continua como padrão e como referência. O backend vem de `VLADE_VECTOR_INDEX__BACKEND`. A suíte de contrato cobre memória, pgvector e Qdrant, e um teste de integração compara o Recall@10 dos dois índices no mesmo espaço.

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

## [0.3.0] - 2026-11-21

### Adicionado

- Métricas de recuperação sem LLM (Recall@K, Precision@K, MRR e NDCG@K) e o comando `vlade-rag eval run`, com o relatório da configuração completa. A pasta `evals/reports/` guarda a linha de base da fase 1 no dataset `legal-ptbr`.
- Reranker por API (`ApiReranker`, ADR-0018): chama o endpoint `/rerank` do OpenRouter ou de um provedor compatível, sem dependência nova. Configuração: `retrieval.rerank.provider: openrouter` e `retrieval.rerank.model`. O comando `vlade-rag eval run` aceita `--rerank-model` e `--rerank-provider` para medir um modelo sem mudar a base. Com o reranker, o Recall@1 no `legal-ptbr` sobe de 0,70 para 0,95 e a pergunta 20 passa para a posição 1.
- Transformadores de consulta (`query_transform`: `rewrite`, `multi_query` e `hyde`, ADR-0019): usam o LLM da base e fundem as consultas derivadas com RRF. A consulta original sempre roda e o reranker a usa. Se o LLM falha, a busca segue com a consulta original. Os valores padrão não mudam.
- Retriever fuzzy com `pg_trgm` (`retrievers: [dense, lexical, fuzzy]`). A migração 0002 cria a função que monta o índice trigram na primeira busca fuzzy. Quem atualiza uma instalação roda `vlade-rag db upgrade`.
- Retriever `bm25` com `pg_search` (ParadeDB, AGPL-3.0), na imagem opcional `vlade-postgres-bm25` (`deploy/postgres/Dockerfile.bm25`, ADR-0022). A migração 0003 cria as funções da busca. A primeira busca `bm25` cria a extensão e o índice. No Compose, a imagem muda com `POSTGRES_DOCKERFILE` e `POSTGRES_IMAGE`. Sem `pg_search`, o retriever `bm25` devolve uma mensagem que cita a imagem. A CI roda os testes do retriever contra a imagem.
- Motor de consulta LangGraph (extra `langgraph`, ADR-0023). A seção `orchestration` da configuração da base escolhe o motor (`pipeline` ou `langgraph`). Ela também liga duas arestas condicionais. A primeira reescreve a consulta uma vez quando o melhor resultado é fraco (`rewrite_below_score`). A segunda busca de novo com mais chunks quando a resposta não tem fundamento (`max_attempts`, `retry_top_k_factor`). Com as arestas desligadas, os dois motores dão a mesma resposta.
- Gate de qualidade (RF-73, ADR-0024): `vlade-rag eval gate` mede a recuperação em bases descartáveis, sem provedor, e falha se uma métrica cai mais que o limite de `evals/gate/gate.json`. A opção `--update-baseline` grava a linha de base. A CI roda o gate em todo pull request.
- Avaliação de respostas com RAGAS (extra `eval`, RF-71, ADR-0025): `vlade-rag eval answers` roda cada pergunta pelo fluxo da base. Um LLM juiz mede faithfulness, answer relevancy, context precision e context recall. O padrão usa o OpenRouter, com o raciocínio do juiz desligado.
- Arize Phoenix no lugar do Langfuse (ADR-0026). O serviço `phoenix` entra no Compose, no perfil `phoenix`. Os spans de IA ganham os atributos OpenInference e um span raiz por consulta. `vlade-rag eval publish` publica uma avaliação como experimento. `VLADE_OTEL__METRICS` e `VLADE_OTEL__PROJECT` são novos, e a CLI também envia traces.
- `vlade-rag eval run` aceita `--retrievers` e `--query-transform`. O dataset `legal-ptbr` ganhou duas variantes das perguntas, com erros de digitação e com paráfrases, e o script `scripts/datasets/derive_legal_ptbr_variants.py`.
- Dataset `legal-ptbr-v2`: 150 documentos de 4 leis (LGPD, CDC, Marco Civil da Internet e Lei de Acesso à Informação) e 109 perguntas formais e coloquiais. Algumas perguntas têm dois ou mais documentos relevantes. Há uma variante com erros de digitação. Cada pergunta nova traz evidências conferidas no texto do artigo. O script `scripts/datasets/summarize_by_group.py` resume um relatório por grupo e por estilo.
- Reranker local (`SentenceTransformersReranker`, extra `local-models`): um cross-encoder do `sentence-transformers` que roda no processo do servidor, sem enviar texto para fora. Configuração: `retrieval.rerank.provider: sentence-transformers` e `VLADE_PROVIDERS__LOCAL_MODELS__DEVICE`, `__BATCH_SIZE` e `__MAX_LENGTH`. O modelo padrão `BAAI/bge-reranker-v2-m3` ocupa cerca de 2,3 GB de memória. O extra puxa o PyTorch e fica fora do extra `server`.
- Benchmark de latência e de vazão (`scripts/benchmarks/bench.py`, subcomandos `search`, `ttft`, `ingest` e `info`). O script mede a busca, o tempo até o primeiro token e a vazão de ingestão, com o tempo de cada etapa. Os relatórios estão em `evals/reports/fase3-benchmark/`. O ADR-0020 (proposto) trata das metas que falharam.

### Corrigido

- O `build_runtime` recebia o tracer e não o passava aos casos de uso. Só o span HTTP da API chegava ao coletor de traces.

## [0.2.0] - 2026-11-21

### Adicionado

- Provedores remotos prontos: OpenRouter, OpenCode Zen e qualquer API compatível com a OpenAI por variável de ambiente.
- `VLADE_DEFAULT_KB_CONFIG`: configuração padrão das bases novas, com mesclagem parcial.
- Cotas por tenant de documentos e de bytes, com `GET /v1/usage`, `vlade-rag usage` e `vlade-rag tenant quota`. Um arquivo acima da cota recebe `quota_exceeded` (HTTP 413).
- Lista e revogação de chaves de API: `vlade-rag key list` e `vlade-rag key revoke`.
- Limite de requisições por chave e por tenant (token bucket) e cota de requisições por dia. Uma chamada acima do limite recebe `rate_limited` (HTTP 429) com `Retry-After`. Configuração: `VLADE_LIMITS__RATE_PER_KEY_PER_MINUTE`, `VLADE_LIMITS__RATE_PER_TENANT_PER_MINUTE` e `vlade-rag tenant quota --requests-per-day`.
- Adapters Valkey (extra `cache`, `redis-py`): cache e limite de requisições compartilhados entre processos, ligados por `VLADE_CACHE__URL`. O Compose já usa o serviço `valkey`. `GET /health/ready` confere o cache.
- Cache de resultados de busca por base e por `kb_epoch`, com validade de 10 minutos.
- Servidor MCP (extra `mcp`, SDK oficial): ferramentas `vlade_list_knowledge_bases`, `vlade_search`, `vlade_query`, `vlade_get_document` e `vlade_get_ingestion_status`, resources `vlade://kb/{slug}` e `vlade://kb/{slug}/documents/{id}` e os prompts `vlade_answer_with_citations` e `vlade_summarize_document`. Transportes `stdio` e Streamable HTTP (`vlade-rag mcp serve`). A chave de API define o tenant e o papel. Cada chamada tem limite por grupo e grava um evento de auditoria com `interface = mcp`. O serviço `mcp` do Compose roda nos perfis `staging` e `prod`.
- Armazenamento de objetos pela API S3 (extra `s3`, `boto3`): `VLADE_OBJECT_STORAGE__BACKEND=s3` com AWS ou qualquer serviço compatível. O `GET /health/ready` confere o bucket. Os três adapters (memória, arquivos e S3) passam no mesmo contrato do port, e todos recusam chaves inseguras. O MinIO deixou de ser o serviço de exemplo (ADR-0017).
- Serviço `rustfs` no Compose (RustFS 1.0.6, Apache-2.0, ADR-0021) nos perfis `s3`, `staging` e `prod`. No notebook: `docker compose --profile dev --profile s3 up`. A CI roda o contrato do `ObjectStorage` contra um container do RustFS.
- Provedor Gemini pelo endpoint compatível com a API da OpenAI (`GEMINI_API_KEY`). A opção `embedding_dimensions` de cada provedor compatível envia `dimensions` nos embeddings.
- Agent Skill `skills/vlade-rag/` no padrão agentskills.io, com as regras de uso das ferramentas `vlade_*`.
- Teste do servidor MCP com o MCP Inspector em modo CLI (`scripts/mcp_inspector.sh`), no job `MCP server (Inspector)` da CI.
- Leitura da auditoria: `GET /v1/audit-events` e `vlade-rag audit list`. Eventos novos: cota negada, cota alterada, chave emitida e chave revogada.

## [0.1.0] - 2026-11-19

### Adicionado

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

### Corrigido

- As políticas de RLS tratam `app.tenant_id` vazio como ausência de tenant.
- Os filtros de metadados no PostgreSQL não codificam mais o JSON duas vezes.

## [0.0.1] - 2026-11-19

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
