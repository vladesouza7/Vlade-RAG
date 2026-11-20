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
| 2 | Interfaces e armazenamento | `0.2.0` | Não iniciada |
| 3 | Qualidade | `0.3.0` | Não iniciada |
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
| 2.1 | Chaves de API, papéis, cotas | ARCHITECTURE §15 |
| 2.2 | Limite de requisições com Valkey | ADR-0007 |
| 2.3 | Auditoria | ARCHITECTURE §7.2 |
| 2.4 | `ObjectStorage` S3 e MinIO no perfil `staging` | ADR-0006 |
| 2.5 | `Cache` Valkey para embeddings de consulta e resultados de busca | ARCHITECTURE §11.6 |
| 2.6 | Provedores Gemini e OpenRouter | VLADE-RAG §16 |
| 2.7 | Servidor MCP com as ferramentas de leitura, resources e prompts | MCP_SPEC §5.2 a §5.6, §6, §7 |
| 2.8 | Teste do servidor MCP com o MCP Inspector na CI | MCP_SPEC §12 |
| 2.9 | Agent Skill `skills/vlade-rag/` | VLADE-RAG §12.1 |
| 2.10 | Teste de isolamento para o MCP | RNF-07 |

**Critérios de aceite:**

- Dois clientes MCP diferentes, por exemplo Claude Code e Hermes Agent, consultam uma base com a Agent Skill instalada.
- Uma chave de outro tenant recebe `not_found` em cada ferramenta MCP e em cada endpoint.
- O limite de requisições devolve `rate_limited` acima do limite configurado.

### Fase 3 — Qualidade

| # | Tarefa | Referência |
|---|---|---|
| 3.1 | Reranker com sentence-transformers e `bge-reranker-v2-m3` | ADR-0008 |
| 3.2 | Transformadores de consulta: reescrita, multi-query, HyDE | ARCHITECTURE §5 |
| 3.3 | Retriever fuzzy (`pg_trgm`) | RF-21 |
| 3.4 | Adapter BM25 com `pg_search` e imagem `vlade-postgres-bm25` | ADR-0005 |
| 3.5 | Fluxo de consulta em LangGraph e teste de igualdade com o pipeline linear | ARCHITECTURE §12.1 |
| 3.6 | Métricas de recuperação: Recall@K, Precision@K, MRR, NDCG | RF-70 |
| 3.7 | Avaliação com RAGAS | RF-71 |
| 3.8 | Langfuse: traces, prompts versionados, experimentos | ADR-0015 |
| 3.9 | Gate de qualidade na CI | RF-73 |
| 3.10 | Benchmark de latência e de vazão | RNF-01 a RNF-04 |

**Critérios de aceite:**

- Um relatório compara a configuração da fase 1 com a melhor configuração da fase 3 no mesmo dataset. O relatório mostra Recall@10, NDCG@10 e faithfulness.
- O benchmark mede RNF-01 a RNF-04. Se uma meta falha, um ADR registra a meta nova ou o plano de correção.

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
