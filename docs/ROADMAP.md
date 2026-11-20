# Vlade-RAG — Roadmap

> Versão 1.0 — 2026-11-19
> Fonte: seção 20 do [`VLADE-RAG.md`](../VLADE-RAG.md). Requisitos: [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

---

## 1. Regras

1. As fases seguem a ordem abaixo. Uma fase só começa depois de a fase anterior cumprir todos os critérios de aceite.
2. Uma tarefa só está concluída quando os testes da tarefa passam na CI.
3. No fim de cada fase, publique uma versão no `CHANGELOG.md` e crie uma tag Git.
4. Se a fase não cumpre um critério de aceite, registre o motivo nesta página e proponha uma ação ao mantenedor.

## 2. Situação

| Fase | Nome | Versão | Situação |
|---|---|---|---|
| 0 | Fundação | `0.0.x` | Tarefas 0.1 a 0.10 concluídas em 2026-11-19. A CI passou no GitHub em 2026-11-19, inclusive licenças, linter de documentação e `GET /health/live` no perfil `dev`. Falta medir o consumo de memória do perfil `dev` (RNF-11). A fase está integrada na branch `homolog` |
| 1 | Núcleo mínimo | `0.1.0` | Em andamento. Tarefas 1.1 a 1.21 implementadas em 2026-11-19. A CI passou no GitHub em 2026-11-19 (PR #1) e a fase está integrada na branch `homolog`. O teste de aceite rodou em 2026-11-19 com o OpenRouter: 100 documentos ingeridos, 19 de 20 perguntas respondidas com a citação certa, 121 testes aprovados e cobertura de 88,40%. Falta a revisão humana das 20 respostas e o teste do Docling (tarefa 1.9). A limitação L1 está registrada na seção da fase |
| 2 | Interfaces e armazenamento | `0.2.0` | Em andamento. Tarefas 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8, 2.9 e 2.10 implementadas. Elas cobrem cotas, chaves, auditoria, limite de requisições, cache no Valkey, Gemini, servidor MCP de leitura, teste com o Inspector e Agent Skill. A tarefa 2.4 está parcial: o adapter S3 está pronto e falta o serviço S3 de exemplo. O critério de aceite ainda não rodou. Ele pede dois clientes MCP reais com a skill instalada |
| 3 | Qualidade | `0.3.0` | Em andamento. Tarefa 3.6 implementada em 2026-11-20. A linha de base da fase 1 está em `evals/reports/` (Recall@10 de 1,00 e MRR de 0,786) |
| 4 | Operação | `0.4.0` | Não iniciada |
| 5 | Extensões | `1.0.0` | Não iniciada |

## 3. Dependências entre fases

```text
F0 Fundação
 └─► F1 Núcleo mínimo
      └─► F2 Interfaces e armazenamento
           ├─► F3 Qualidade
           │    └─► F4 Operação
           │         └─► F5 Extensões
           └─► (MCP de escrita depende de F2 auth e entra em F4)
```

## 4. Fases

### Fase 0 — Fundação

| # | Tarefa | Referência |
|---|---|---|
| 0.1 | Documentos fundadores: `PROJECT_SPEC.md`, `ARCHITECTURE.md`, `MCP_SPEC.md`, `ROADMAP.md` | Concluída |
| 0.2 | ADRs 0001 a 0015 | Concluída |
| 0.3 | Arquivos open source: `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, templates de issue e de pull request | ADR-0001 · Concluída |
| 0.4 | Workspace `uv` com `packages/python` e workspace Cargo com `packages/rust/vlade_rag_core` | ADR-0003 · Concluída |
| 0.5 | Esqueleto dos módulos da seção 3 do `ARCHITECTURE.md`, com `__init__.py` e testes vazios | ARCHITECTURE §3 · Concluída |
| 0.6 | CI no GitHub Actions: `ruff`, `mypy --strict` no `core`, `pytest`, `cargo clippy`, `cargo fmt --check`, build das duas distribuições | RNF-05, RNF-10 · Concluída |
| 0.7 | Verificação de licenças na CI (`pip-licenses` e `cargo-deny`) | ADR-0001 · Concluída |
| 0.8 | Linter da skill `asd-ste100-pt-br` na CI para `docs/` e `skills/` | CLAUDE.md · Concluída |
| 0.9 | `docker-compose.yml` com o perfil `dev`: `api`, `postgres`, `valkey` | ARCHITECTURE §17 · Concluída |
| 0.10 | Endpoint `/health/live` | ARCHITECTURE §14.1 · Concluída |

**Critérios de aceite:**

- A CI passa, inclusive a verificação de licenças e o linter de documentação.
- `docker compose --profile dev up` sobe a API. `GET /health/live` responde 200.
- O consumo de memória do perfil `dev` fica em até 3 GB (RNF-11).

### Fase 1 — Núcleo mínimo

| # | Tarefa | Referência |
|---|---|---|
| 1.1 | Domínio: entidades, objetos de valor, erros | ARCHITECTURE §4 · Concluída |
| 1.2 | Ports e suítes de contrato em `vlade_rag.testing.contracts` | ARCHITECTURE §5 · Concluída |
| 1.3 | Adapters em memória de todos os ports usados na fase 1 | ARCHITECTURE §2 · Concluída |
| 1.4 | Configuração tipada e registro de plugins | ARCHITECTURE §9 · Concluída |
| 1.5 | Motor Rust: `normalize_text`, `split_text`, `load_tokenizer`, `count_tokens`, `content_hash`, `simhash`, `rrf_fuse` | ADR-0003 · Concluída |
| 1.6 | Implementação de reserva em Python e teste de propriedade | ARCHITECTURE §8.2 · Concluída |
| 1.7 | Migrações Alembic, RLS e papéis do banco | ARCHITECTURE §7, ADR-0012 · Concluída |
| 1.8 | Adapters PostgreSQL: `KnowledgeRepository`, `VectorIndex` (pgvector), `LexicalIndex` (`tsvector`) | ADR-0004, ADR-0005 · Concluída |
| 1.9 | Parsers: texto, Markdown, HTML, PDF e DOCX com Docling | ADR-0010 · Implementada. Falta o teste com o Docling instalado |
| 1.10 | `ObjectStorage` no sistema de arquivos | ADR-0006 · Concluída |
| 1.11 | Embeddings: Ollama, API compatível com OpenAI | ADR-0008 · Concluída |
| 1.12 | LLM: Ollama, API compatível com OpenAI | VLADE-RAG §16 · Concluída |
| 1.13 | Pipeline de ingestão, fila de jobs e worker | ARCHITECTURE §10 · Concluída |
| 1.14 | Casos de uso `CreateKnowledgeBase`, `SubmitIngestion`, `RunIngestionJob`, `GetIngestionStatus`, `Search`, `AnswerQuery`, `GetDocument`, `DeleteDocument` | ARCHITECTURE §6 · Concluída |
| 1.15 | Pipeline de consulta linear, montagem de contexto, citações e validação | ARCHITECTURE §11 · Concluída |
| 1.16 | Prompts padrão em pt-BR e em inglês | RF-34 · Concluída |
| 1.17 | API REST, inclusive streaming SSE | ARCHITECTURE §14.1 · Concluída |
| 1.18 | CLI | ARCHITECTURE §14.3 · Concluída |
| 1.19 | OpenTelemetry: spans, métricas e logs JSON | ARCHITECTURE §16 · Concluída |
| 1.20 | Teste de isolamento entre tenants para API e CLI | RNF-07 · Concluída |
| 1.21 | Dataset de exemplo em pt-BR com 100 documentos de domínio público | `evals/datasets/` · Concluída |

**Critérios de aceite:**

- Um usuário ingere os 100 documentos do dataset de exemplo pela CLI.
- `vlade-rag query` responde a 20 perguntas do dataset com citações. Cada citação aponta para um chunk que contém a informação citada. Uma pessoa confere as 20 respostas.
- O teste de isolamento passa.
- As suítes de contrato passam para cada adapter.
- A cobertura de testes de `core`, `retrieval` e `ingestion` fica em 85% ou mais.

**Resultado do teste de aceite (2026-11-19):**

- Provedores: embeddings `openai/text-embedding-3-small` e geração `tencent/hy4-flash`, pelo OpenRouter.
- A CLI ingeriu os 100 documentos em 1 min 21 s.
- 19 das 20 perguntas receberam a resposta esperada, com citação do documento relevante. A revisão humana das 20 respostas continua pendente.
- O teste de isolamento e as suítes de contrato passaram com o PostgreSQL. A cobertura total é de 88,40%.

**Limitações conhecidas:**

| ID | Limitação | Efeito | Tratamento |
|---|---|---|---|
| L1 | A recuperação da fase 1 usa só busca vetorial e lexical com fusão simples. Uma palavra comum em muitos documentos faz o trecho da definição cair abaixo da posição 8 | A pergunta 20 do dataset ("O que é fornecedor segundo o CDC?") recebeu "Não encontrei essa informação nas fontes disponíveis". O `cdc-001` ficou na posição 10. O sistema recusou e não inventou resposta | Fase 3: tarefas 3.1 (reranker) e 3.2 (reescrita de consulta). Depois, repita a pergunta 20 |

### Fase 2 — Interfaces e armazenamento

| # | Tarefa | Referência |
|---|---|---|
| 2.1 | Chaves de API, papéis, cotas | ARCHITECTURE §15 · Implementada em 2026-11-19: cotas de documentos, de bytes e de requisições por dia, lista e revogação de chaves, `GET /v1/usage` |
| 2.2 | Limite de requisições com Valkey | ADR-0007 · Implementada em 2026-11-19: token bucket por chave e por tenant (`VLADE_LIMITS__RATE_PER_KEY_PER_MINUTE` e `VLADE_LIMITS__RATE_PER_TENANT_PER_MINUTE`), `rate_limited` com `Retry-After` na API e cota diária. O servidor MCP (2.7) aplica o mesmo limite |
| 2.3 | Auditoria | ARCHITECTURE §7.2 · Implementada em 2026-11-19: eventos de cota negada, de cota alterada e de chave emitida ou revogada, `GET /v1/audit-events` e `vlade-rag audit list`. Ver a limitação L2 |
| 2.4 | `ObjectStorage` S3 e MinIO no perfil `staging` | ADR-0006, ADR-0017 · Parcial em 2026-11-20: o adapter S3 (extra `s3`, `boto3`) está pronto e passa no contrato do port com `moto`. O MinIO deixou de ser distribuído (ADR-0017). Falta o serviço S3 de exemplo no Compose (RustFS ou SeaweedFS) e o contrato rodando contra um serviço real. Ver a limitação L7 |
| 2.5 | `Cache` Valkey para embeddings de consulta e resultados de busca | ARCHITECTURE §11.6 · Implementada em 2026-11-19: `ValkeyCache` (extra `cache`), cache de resultados de busca com `kb_epoch` e `VLADE_CACHE__URL` no Compose. Ver a limitação L4 |
| 2.6 | Provedores Gemini e OpenRouter | VLADE-RAG §16 · Implementada em 2026-11-20. O OpenRouter vem da fase 1. O Gemini usa o endpoint compatível com a API da OpenAI (provedor `gemini`, `GEMINI_API_KEY`). Os testes usam um cliente HTTP falso: nenhuma chamada real ao Google rodou. Ver a limitação L8 |
| 2.7 | Servidor MCP com as ferramentas de leitura, resources e prompts | MCP_SPEC §5.2 a §5.6, §6, §7 · Implementada em 2026-11-19: 5 ferramentas de leitura, 2 resources, 2 prompts, transportes `stdio` e Streamable HTTP, papel por ferramenta, limites por grupo e auditoria. Serviço `mcp` no Compose (`staging` e `prod`). Ver as limitações L5 e L6 |
| 2.8 | Teste do servidor MCP com o MCP Inspector na CI | MCP_SPEC §12 · Implementada em 2026-11-20: job `MCP server (Inspector)` e `scripts/mcp_inspector.sh` (Inspector 2.16.0, modo CLI, 24 verificações). O teste achou um erro do servidor: o resultado de erro trazia `structuredContent` fora do `outputSchema`. Corrigido |
| 2.9 | Agent Skill `skills/vlade-rag/` | VLADE-RAG §12.1 · Implementada em 2026-11-20: `skills/vlade-rag/SKILL.md` no padrão agentskills.io, sem violações duras no linter. Falta instalar a skill em dois clientes reais (critério de aceite da fase) |
| 2.10 | Teste de isolamento para o MCP | RNF-07 · Concluída em 2026-11-19: `tests/e2e/test_mcp_isolation.py` chama cada ferramenta e cada resource com a chave de um tenant e os identificadores de outro. A resposta é `not_found` e é igual à resposta de um identificador que não existe |

**Critérios de aceite:**

- Dois clientes MCP diferentes, por exemplo Claude Code e Hermes Agent, consultam uma base com a Agent Skill instalada.
- Uma chave de outro tenant recebe `not_found` em cada ferramenta MCP e em cada endpoint.
- O limite de requisições devolve `rate_limited` acima do limite configurado.

**Limitações conhecidas:**

| ID | Limitação | Efeito | Tratamento |
|---|---|---|---|
| L2 | Os casos de uso gravam o `AuditEvent` logo depois da escrita, em outra transação. Só as operações de cotas e de chaves (`TenantDirectory`) gravam o evento na mesma transação | Se o processo cai entre a escrita e o evento, a escrita fica sem evento de auditoria | Introduzir uma unidade de trabalho (transação compartilhada entre repositório e auditoria) com um ADR. Ainda sem tarefa |
| L3 | Os casos de uso não gravam evento para uma chamada negada por papel insuficiente (`PermissionDenied`). O servidor MCP já grava o evento `denied`. A API REST ainda não grava | Uma tentativa sem permissão na API REST não aparece na auditoria | Gravar o evento também na camada da API REST. Ainda sem tarefa |
| L5 | O servidor MCP não envia notificações de progresso durante `vlade_query` (MCP_SPEC §5.4) | Um cliente que informa `progressToken` não recebe o progresso. A resposta final funciona | Enviar o progresso pelo `Context` do SDK, quando houver streaming de resposta pelo MCP |
| L6 | Os limites por grupo do MCP (MCP_SPEC §8) são fixos no código. A configuração do tenant ainda não muda os valores | Um tenant não ajusta os limites do MCP | Ler `tenants.settings.mcp.rate_limits`. Ainda sem tarefa |
| L7 | O Compose não traz um serviço S3. Ninguém rodou o container do RustFS nem o do SeaweedFS com o contrato do port | Quem usa `staging` aponta para um S3 existente com as variáveis `S3_*`. A compatibilidade com cada serviço compatível não está medida | Subir o serviço escolhido no Compose e na CI e rodar o contrato com `VLADE_TEST_S3_*` (tarefa 2.4) |
| L8 | A documentação do Google não confirma o campo `dimensions` nos embeddings do endpoint compatível. O `gemini-embedding-001` tem 3072 dimensões por padrão, e o índice HNSW do pgvector aceita até 2000 | Sem `dimensions`, os embeddings do Gemini podem não caber no índice. Ninguém testou o Gemini com uma chave real | Testar com uma chave real. Se o campo falhar, usar `halfvec` ou outro modelo de embedding |
| L4 | Se o Valkey falha, o cache perde a entrada e o limite de requisições deixa a requisição passar (ADR-0007). A API lê as cotas do tenant no banco a cada requisição, para conferir `requests_per_day` | Sem Valkey, o limite e a cota diária não protegem. Há uma leitura extra no banco por requisição | Monitorar o Valkey. Guardar as cotas no cache por alguns segundos, se a leitura pesar. Ainda sem tarefa |

### Fase 3 — Qualidade

| # | Tarefa | Referência |
|---|---|---|
| 3.1 | Reranker com sentence-transformers e `bge-reranker-v2-m3` | ADR-0008 |
| 3.2 | Transformadores de consulta: reescrita, multi-query, HyDE | ARCHITECTURE §5 |
| 3.3 | Retriever fuzzy (`pg_trgm`) | RF-21 |
| 3.4 | Adapter BM25 com `pg_search` e imagem `vlade-postgres-bm25` | ADR-0005 |
| 3.5 | Fluxo de consulta em LangGraph e teste de igualdade com o pipeline linear | ARCHITECTURE §12.1 |
| 3.6 | Métricas de recuperação: Recall@K, Precision@K, MRR, NDCG | RF-70 · Implementada em 2026-11-20: `vlade_rag.evaluation`, `vlade-rag eval run` e o relatório de linha de base da fase 1 em `evals/reports/`. Ver a limitação L9 |
| 3.7 | Avaliação com RAGAS | RF-71 |
| 3.8 | Langfuse: traces, prompts versionados, experimentos | ADR-0015 |
| 3.9 | Gate de qualidade na CI | RF-73 |
| 3.10 | Benchmark de latência e de vazão | RNF-01 a RNF-04 |

**Critérios de aceite:**

- Um relatório compara a configuração da fase 1 com a melhor configuração da fase 3 no mesmo dataset. O relatório mostra Recall@10, NDCG@10 e faithfulness.
- O benchmark mede RNF-01 a RNF-04. Se uma meta falha, um ADR registra a meta nova ou o plano de correção.

**Linha de base (2026-11-20):** busca densa e léxica com RRF, sem reranker, no dataset `legal-ptbr`. Recall@1 de 0,70, Recall@10 de 1,00, MRR de 0,786 e NDCG@10 de 0,838. A pergunta 20 traz o documento certo na posição 9. O detalhe está em `evals/reports/README.md`.

**Limitações conhecidas:**

| ID | Limitação | Efeito | Tratamento |
|---|---|---|---|
| L9 | A avaliação roda só pela CLI (`vlade-rag eval run`), de forma síncrona e no nível do documento. O caso de uso `RunEvaluation` (job, `POST /v1/evaluations`) não existe | Não dá para agendar a avaliação nem chamar pela API | Tarefas 3.9 (gate na CI) e 4.1 (flow `evaluate_nightly`) |

### Fase 4 — Operação

| # | Tarefa | Referência |
|---|---|---|
| 4.1 | Flows Kestra: `ingest_batch`, `reindex_knowledge_base`, `evaluate_nightly`, `backup` | ARCHITECTURE §12.2, ADR-0011 |
| 4.2 | Reindexação sem parada nos modos `embeddings` e `full` | ARCHITECTURE §13 |
| 4.3 | Ferramentas MCP de escrita com confirmação | MCP_SPEC §5.7 a §5.10 |
| 4.4 | Módulo `ops`: recuperação de jobs vencidos, limpeza de versões antigas, health checks | ARCHITECTURE §10 |
| 4.5 | Grafana Alloy, Prometheus, Loki, Tempo e Grafana no perfil `prod` | ADR-0015 |
| 4.6 | Cinco dashboards e alertas | VLADE-RAG §14 |
| 4.7 | Guia de implantação em `docs/operacao/` | — |

**Critérios de aceite:**

- Uma reindexação completa roda pelo Kestra enquanto um teste de carga faz consultas. Nenhuma consulta falha. Nenhuma consulta mistura espaços de embeddings.
- Os cinco dashboards mostram dados reais.
- Cada alerta dispara em um teste de falha provocada.

### Fase 5 — Extensões

| # | Tarefa | Referência |
|---|---|---|
| 5.1 | Adapter Qdrant e suíte de contrato | ADR-0004 |
| 5.2 | Conectores de origem: Google Drive, sites, bancos SQL | `DocumentSource` |
| 5.3 | Flow Kestra `sync_source` | ARCHITECTURE §12.2 |
| 5.4 | Cache semântico | — |
| 5.5 | OIDC e OAuth 2.1 na API e no MCP | MCP_SPEC §3.2 |
| 5.6 | Publicação no PyPI com wheels de todas as plataformas | RNF-09 |
| 5.7 | Site de documentação | — |

**Critérios de aceite:**

- O mesmo dataset dá métricas de recuperação equivalentes com pgvector e com Qdrant. A diferença de Recall@10 fica em até 2 pontos percentuais.
- `pip install "vlade-rag[all]"` funciona nas plataformas de RNF-09.

## 5. Riscos

| Risco | Efeito | Ação |
|---|---|---|
| A memória do notebook de 8 GB não comporta os testes de integração | Desenvolvimento lento | Perfis do Compose. Testes pesados no HomeLab |
| Qualidade baixa de embeddings em pt-BR | Recuperação ruim | Dataset em pt-BR desde a fase 1. Comparação de modelos na fase 3 |
| Mudança de licença de um serviço externo | Conflito com a política MIT | Ports genéricos. Verificação de licenças na CI. Revisão anual dos ADRs de licença |
| Mudança na especificação do MCP | Clientes incompatíveis | SDK oficial. Teste com o MCP Inspector. Teste manual com dois clientes por release |
| Custo dos provedores de LLM nas avaliações | Avaliação cara | Métricas sem LLM na CI. RAGAS só por agenda |
| Desempenho do índice HNSW parcial com muitos espaços | Latência alta | Benchmark na fase 3. Limite de espaços ativos por tenant |
| Escopo grande para um mantenedor | Atraso | Fases curtas. Cada fase entrega uma versão utilizável |
