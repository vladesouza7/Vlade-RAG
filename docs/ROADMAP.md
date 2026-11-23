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
| 0 | Fundação | `0.0.x` | Tarefas 0.1 a 0.10 concluídas em 2026-11-19. A CI passou no GitHub em 2026-11-19, inclusive licenças, linter de documentação e `GET /health/live` no perfil `dev`. O consumo de memória do perfil `dev` foi medido em 2026-11-21: pico de 166 MiB somando `api`, `postgres` e `valkey`, abaixo do limite de 3 GB (RNF-11). A fase está integrada na branch `homolog` |
| 1 | Núcleo mínimo | `0.1.0` | Em andamento. Tarefas 1.1 a 1.21 implementadas em 2026-11-19. A CI passou no GitHub em 2026-11-19 (PR #1) e a fase está integrada na branch `homolog`. O teste de aceite rodou em 2026-11-19 com o OpenRouter: 100 documentos ingeridos, 19 de 20 perguntas respondidas com a citação certa, 121 testes aprovados e cobertura de 88,40%. Falta a revisão humana das 20 respostas e o teste do Docling (tarefa 1.9). A limitação L1 está registrada na seção da fase |
| 2 | Interfaces e armazenamento | `0.2.0` | Em andamento. Tarefas 2.1 a 2.10 implementadas. Elas cobrem cotas, chaves, auditoria, limite de requisições, armazenamento S3 com o RustFS, cache no Valkey, Gemini, servidor MCP de leitura, teste com o Inspector e Agent Skill. A tarefa 2.4 está concluída em 2026-11-21 com o RustFS (ADR-0021). O critério de aceite ainda não rodou. Ele pede dois clientes MCP reais com a skill instalada |
| 3 | Qualidade | `0.3.0` | Em andamento. Tarefas 3.2, 3.3 e 3.6 implementadas em 2026-11-20. A linha de base da fase 1 está em `evals/reports/` (Recall@10 de 1,00 e MRR de 0,786). A tarefa 3.1 está implementada: o reranker por API está medido, e o adapter local está pronto sem medida do modelo real. Com o reranker, o Recall@1 sobe de 0,70 para 0,95 e a pergunta 20 passa para a posição 1. Fuzzy, reescrita, multi-query e HyDE não melhoram o resultado com o reranker ligado no `legal-ptbr`. O `legal-ptbr-v2` (150 documentos, 109 perguntas) tira o reranker do teto: com `mongodb/rerank-2.5`, o MRR é 0,959. No v2, o fuzzy e o HyDE melhoram a busca sem reranker e não mudam nada com ele (L12). A tarefa 3.10 está parcial: nenhuma meta de latência de busca foi cumprida nesta máquina (ADR-0020, proposto). A tarefa 3.4 está concluída em 2026-11-21: com 102 mil chunks, o retriever `bm25` leva 60 ms de p95, e o `tsvector` leva 6,813 s. A tarefa 3.5 está concluída em 2026-11-21: o motor LangGraph dá a mesma resposta do pipeline linear com as arestas desligadas. A tarefa 3.9 está concluída em 2026-11-21: a CI roda o gate de qualidade. As tarefas 3.7 (RAGAS) e 3.8 (Arize Phoenix no lugar do Langfuse) estão concluídas em 2026-11-21. O critério de aceite está cumprido com o `legal-ptbr` e o `legal-ptbr-v2`. No `legal-ptbr-v2`, o Recall@10 sobe de 0,979 para 1,000 e a faithfulness de 0,904 para 0,934. Falta a parte restante da tarefa 3.10 |
| 4 | Operação | `0.4.0` | Concluída em 2026-11-23. Tarefas 4.1 a 4.7 integradas em `homolog`. A reindexação com carga passou sem falha de consulta e sem mistura de espaços. Os cinco dashboards mostraram dados reais e os oito alertas dispararam em testes provocados na CI. A versão `0.4.0` está no CHANGELOG e a tag `v0.4.0` marca o release |
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
- O consumo de memória do perfil `dev` fica em até 3 GB (RNF-11). Medido em 2026-11-21: pico de 166 MiB somando `api`, `postgres` e `valkey`, com 550 buscas concorrentes. Relatório em `evals/reports/fase4-memoria/`.

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
| L1 | A recuperação da fase 1 usa só busca vetorial e lexical com fusão simples. Uma palavra comum em muitos documentos faz o trecho da definição cair abaixo da posição 8 | A pergunta 20 do dataset ("O que é fornecedor segundo o CDC?") recebeu "Não encontrei essa informação nas fontes disponíveis". O `cdc-001` ficou na posição 10. O sistema recusou e não inventou resposta | Resolvida na fase 3 (2026-11-21): com o reranker `mongodb/rerank-2.5`, o `cdc-001` fica na posição 1 e a pergunta 20 recebe a resposta certa, com citação (`evals/reports/fase3-ragas/`) |

### Fase 2 — Interfaces e armazenamento

| # | Tarefa | Referência |
|---|---|---|
| 2.1 | Chaves de API, papéis, cotas | ARCHITECTURE §15 · Implementada em 2026-11-19: cotas de documentos, de bytes e de requisições por dia, lista e revogação de chaves, `GET /v1/usage` |
| 2.2 | Limite de requisições com Valkey | ADR-0007 · Implementada em 2026-11-19: token bucket por chave e por tenant (`VLADE_LIMITS__RATE_PER_KEY_PER_MINUTE` e `VLADE_LIMITS__RATE_PER_TENANT_PER_MINUTE`), `rate_limited` com `Retry-After` na API e cota diária. O servidor MCP (2.7) aplica o mesmo limite |
| 2.3 | Auditoria | ARCHITECTURE §7.2 · Implementada em 2026-11-19: eventos de cota negada, de cota alterada e de chave emitida ou revogada, `GET /v1/audit-events` e `vlade-rag audit list`. Ver a limitação L2 |
| 2.4 | `ObjectStorage` S3 e serviço S3 no perfil `staging` | ADR-0006, ADR-0017, ADR-0021 · Concluída em 2026-11-21: o adapter S3 (extra `s3`, `boto3`) passa no contrato do port com `moto` e com o RustFS 1.0.6. O serviço `rustfs` está no Compose (perfis `s3`, `staging` e `prod`), e a CI roda o contrato contra um container do RustFS. A API do perfil `dev` gravou e leu documentos no RustFS. O MinIO deixou de ser distribuído (ADR-0017) |
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
| L7 | Fechada em 2026-11-21. O Compose traz o RustFS, e a CI roda o contrato do port contra ele (ADR-0021). O SeaweedFS e o Garage não têm teste | Um serviço S3 diferente do RustFS e da AWS pode ter uma diferença de compatibilidade sem medida | Rodar o contrato com `VLADE_TEST_S3_*` contra o serviço antes de usar |
| L8 | A documentação do Google não confirma o campo `dimensions` nos embeddings do endpoint compatível. O `gemini-embedding-001` tem 3072 dimensões por padrão, e o índice HNSW do pgvector aceita até 2000 | Sem `dimensions`, os embeddings do Gemini podem não caber no índice. Ninguém testou o Gemini com uma chave real | Testar com uma chave real. Se o campo falhar, usar `halfvec` ou outro modelo de embedding |
| L4 | Se o Valkey falha, o cache perde a entrada e o limite de requisições deixa a requisição passar (ADR-0007). A API lê as cotas do tenant no banco a cada requisição, para conferir `requests_per_day` | Sem Valkey, o limite e a cota diária não protegem. Há uma leitura extra no banco por requisição | Monitorar o Valkey. Guardar as cotas no cache por alguns segundos, se a leitura pesar. Ainda sem tarefa |

### Fase 3 — Qualidade

| # | Tarefa | Referência |
|---|---|---|
| 3.1 | Reranker com sentence-transformers e `bge-reranker-v2-m3` | ADR-0008, ADR-0018 · Implementada em 2026-11-20. O `ApiReranker` (endpoint `/rerank` do OpenRouter) está medido com cinco modelos. O adapter local `SentenceTransformersReranker` (extra `local-models`) tem testes de unidade com um codificador falso. A chamada à biblioteca real foi conferida com um cross-encoder minúsculo. O `bge-reranker-v2-m3` não rodou: a máquina de desenvolvimento não roda modelos locais. Ver as limitações L10 e L11 |
| 3.2 | Transformadores de consulta: reescrita, multi-query, HyDE | ARCHITECTURE §5, ADR-0019 · Implementada em 2026-11-20: `LLMQueryTransformer` com os três modos, prompts em pt-BR e em inglês e consultas derivadas fundidas com RRF. Sem o reranker, o HyDE é a melhor transformação (MRR de 0,786 para 0,854 no dataset original). Com o reranker, as três não mudam o resultado. Ver as limitações L12 e L13 |
| 3.3 | Retriever fuzzy (`pg_trgm`) | RF-21, ADR-0019 · Implementada em 2026-11-20: `TrigramLexicalIndex`, migração 0002 e equivalente em memória. O ganho é pequeno, até com erros de digitação (MRR de 0,729 para 0,754). Ver as limitações L12 e L14 |
| 3.4 | Adapter BM25 com `pg_search` e imagem `vlade-postgres-bm25` | ADR-0005, ADR-0022 · Concluída em 2026-11-21: imagem `vlade-postgres-bm25` (`pg_search` 0.27.0), migração 0003, retriever `bm25` (`PgSearchLexicalIndex`) e job da CI. Com 102 mil chunks, o p95 do `bm25` é de 60 ms, contra 6,813 s do `tsvector`: o critério do ADR-0020 está cumprido. No `legal-ptbr-v2`, o MRR da busca lexical sobe de 0,512 para 0,686. O relatório está em `evals/reports/fase3-bm25/`. Ver as limitações L16 e L18 |
| 3.5 | Fluxo de consulta em LangGraph e teste de igualdade com o pipeline linear | ARCHITECTURE §12.1, ADR-0023 · Concluída em 2026-11-21: o `AnswerQuery` expõe os passos do fluxo, o `PipelineEngine` (padrão) e o `LangGraphEngine` (extra `langgraph`) usam os mesmos passos. A configuração `orchestration` da base escolhe o motor e liga as duas arestas condicionais (reescrita e nova tentativa). O teste de igualdade passa com memória e com PostgreSQL, na resposta e nos eventos de streaming. Ver a limitação L19 |
| 3.6 | Métricas de recuperação: Recall@K, Precision@K, MRR, NDCG | RF-70 · Implementada em 2026-11-20: `vlade_rag.evaluation`, `vlade-rag eval run` e o relatório de linha de base da fase 1 em `evals/reports/`. Ver a limitação L9 |
| 3.7 | Avaliação com RAGAS | RF-71, ADR-0025 · Concluída em 2026-11-21: `vlade-rag eval answers` (extra `eval`, RAGAS 0.4.4) mede faithfulness, answer relevancy, context precision e context recall com um juiz pelo OpenRouter. O relatório do critério de aceite está em `evals/reports/fase3-ragas/`. Ver a limitação L21 |
| 3.8 | Observabilidade de IA: traces e experimentos (Arize Phoenix no lugar do Langfuse) | ADR-0015, ADR-0026 · Concluída em 2026-11-21: serviço `phoenix` no Compose (perfil `phoenix`), atributos OpenInference nos spans, span raiz por consulta, telemetria na CLI e `vlade-rag eval publish` para os experimentos. Corrigido: o `build_runtime` não passava o tracer aos casos de uso. Os prompts versionados no serviço externo ficam de fora (limitação L22) |
| 3.9 | Gate de qualidade na CI | RF-73, ADR-0024 · Concluída em 2026-11-21: `vlade-rag eval gate` cria bases descartáveis em memória com embeddings `hashing` e roda as execuções de `evals/gate/gate.json`. O gate falha se uma métrica cai mais de 0,02 em relação a `evals/gate/baseline.json`. O job `Quality gate (RF-73)` da CI roda o gate em cerca de 1 minuto, sem provedor. Ver a limitação L20 |
| 3.10 | Benchmark de latência e de vazão | RNF-01 a RNF-04 · Parcial em 2026-11-21: `scripts/benchmarks/bench.py` e os relatórios em `evals/reports/fase3-benchmark/`. O benchmark mediu a ingestão e a busca na base real, com três rerankers e com as três transformações de consulta. Ele também mediu a escala até 104 mil chunks e o primeiro token sem o LLM remoto. Com as transformações, o p95 da busca vai de 812 ms para 7,1 s a 10,8 s. Faltam a base de 1 milhão de chunks e o reranker local: a máquina de desenvolvimento não comporta os dois. As metas de RNF-01, RNF-02 e RNF-04 falham em parte. O ADR-0020 (proposto) registra o plano. Ver as limitações L15, L16 e L17 |

**Critérios de aceite:**

- Um relatório compara a configuração da fase 1 com a melhor configuração da fase 3 no mesmo dataset. O relatório mostra Recall@10, NDCG@10 e faithfulness.
- O benchmark mede RNF-01 a RNF-04. Se uma meta falha, um ADR registra a meta nova ou o plano de correção.

**Linha de base (2026-11-20):** busca densa e léxica com RRF, sem reranker, no dataset `legal-ptbr`. Recall@1 de 0,70, Recall@10 de 1,00, MRR de 0,786 e NDCG@10 de 0,838. A pergunta 20 traz o documento certo na posição 9. O detalhe está em `evals/reports/README.md`.

**Reranker por API (2026-11-20):** os cinco modelos do ADR-0018 dão o mesmo resultado no `legal-ptbr`: Recall@1 de 0,95, Recall@10 de 1,00, MRR de 0,975 e NDCG@10 de 0,982. A pergunta 20 passou da posição 9 para a posição 1. A pergunta 5 passou da posição 1 para a 2, porque os modelos preferem o artigo 41 (`lgpd-026`), que também responde à pergunta. O ADR-0018 traz o custo e a latência de cada modelo.

**Transformadores de consulta e fuzzy (2026-11-20):** a medida cobre 3 datasets de 20 perguntas (original, com erros de digitação e com paráfrases). Com o reranker, as quatro combinações dão o mesmo resultado do reranker sozinho. Sem o reranker, o HyDE é a melhor transformação: MRR de 0,786 para 0,854 (original), de 0,729 para 0,775 (erros de digitação) e de 0,498 para 0,681 (paráfrases). A reescrita e o multi-query ajudam só nas paráfrases e pioram o dataset original. O fuzzy sobe o MRR em 0,025 nos erros de digitação. A tabela completa está no ADR-0019, e os 30 relatórios estão em `evals/reports/fase3-consulta-fuzzy/`.

**Dataset `legal-ptbr-v2` (2026-11-21):** 150 documentos de 4 leis e 109 perguntas, formais e coloquiais. Treze perguntas têm dois ou mais documentos relevantes. Há também uma variante com erros de digitação. A linha de base sem reranker fica em MRR 0,740 (0,786 no `legal-ptbr`). Os três rerankers testados ficam entre MRR 0,940 e 0,965, abaixo do teto do dataset antigo (0,975), com a folga nas perguntas coloquiais. Sem reranker, o HyDE sobe o MRR para 0,788 e ajuda as perguntas coloquiais. O fuzzy sobe o MRR para 0,783 e ajuda as perguntas formais. A reescrita sobe o MRR para 0,764. O multi-query piora a busca (MRR 0,691). Com o reranker, as quatro técnicas não mudam as métricas. As 15 medidas estão em `evals/reports/fase3-dataset-v2/`, e as tabelas estão no README do dataset.

**Critério de aceite: fase 1 contra fase 3 (2026-11-21):** o relatório está em `evals/reports/fase3-ragas/`. No `legal-ptbr` (20 perguntas), o reranker sobe o MRR de 0,786 para 0,975 e a context precision de 0,720 para 0,996. O Recall@10 fica em 1,000. A faithfulness fica em 0,950 na fase 1 e em 0,938 na fase 3. A diferença vem de uma nota errada do juiz, e sem ela a fase 3 tem 0,987. Todas as respostas da fase 3 têm citação. No `legal-ptbr-v2` (109 perguntas), o MRR sobe de 0,740 para 0,959 e o Recall@10 de 0,979 para 1,000. A faithfulness sobe de 0,904 para 0,934, e a context precision de 0,697 para 0,902. A faithfulness sobe nas perguntas formais (0,907 para 0,956) e fica estável nas coloquiais (0,896 para 0,887).

**Benchmark (2026-11-21):** o relatório está em `evals/reports/fase3-benchmark/`. Na base real (184 chunks), o p95 da busca é de 812 ms sem reranker. Desses, 787 ms são o embedding remoto da pergunta. Com reranker por API, o p95 é de 1,978 s a 2,229 s. Em uma base sintética, o p95 da busca vai de 408 ms (6 mil chunks) a 7,998 s (104 mil chunks). A busca lexical responde pelo crescimento. A ingestão cumpre a meta de 50 páginas por segundo só com documentos longos: de 56 a 70 com 100 páginas por documento. Com 1 página por documento, ela fica em 8 a 15, por causa de 62 transações por documento. O primeiro token sai logo depois da busca: p95 de 591 ms só com a busca vetorial e de 7,559 s com a configuração padrão. A base de 1 milhão de chunks não cabe nesta máquina. O limite de gasto da chave do OpenRouter acabou antes das transformações com LLM.

**Limitações conhecidas:**

| ID | Limitação | Efeito | Tratamento |
|---|---|---|---|
| L9 | A avaliação de respostas com métricas de juiz pago roda só pela CLI (`vlade-rag eval answers` e `eval gate`), de forma síncrona. A avaliação de recuperação já tem caso de uso (`RunEvaluation`), job, API, MCP e flow agendado | Não dá para agendar as métricas de resposta nem chamá-las pela API ou pelo MCP. A CI roda o gate (tarefa 3.9) com métricas de recuperação | Medir as métricas de resposta em um job com juiz configurado pelo servidor |
| L10 | O `legal-ptbr` (20 perguntas, um documento relevante por pergunta) não separa configurações, porque o reranker o leva ao teto. O `legal-ptbr-v2` resolve isso em parte: os três rerankers ficam entre MRR 0,940 e 0,965, e as perguntas coloquiais têm folga. Cada grupo do v2 tem de 10 a 20 perguntas, e a auditoria do gabarito leu só as perguntas em que os rerankers discordavam | Uma diferença de 0,025 de MRR entre dois rerankers é de poucas perguntas, e o melhor muda de um grupo para outro. O v2 ainda não escolhe o modelo padrão de reranking | Ampliar as perguntas coloquiais. Escolher o modelo padrão de reranking só com mais perguntas, com o custo e com a latência (tarefa 3.10) |
| L11 | O reranker por API envia o texto dos candidatos a um terceiro. Ninguém verificou as licenças e os termos dos cinco modelos testados. A requisição leva de 0,9 s a 1,5 s, e o RNF-02 pede p95 de 1 s. O reranker local não tem medida de qualidade nem de latência, porque a máquina de desenvolvimento não roda modelos locais | Quem não pode enviar o texto para fora tem um reranker sem prova de qualidade. O RNF-02 pode falhar com o reranker por API | Medir o adapter local em uma máquina com mais memória, com o teste desligado por padrão. Verificar as licenças dos cinco modelos (ADR-0008, item 4). A tarefa 3.10 mede o RNF-02 |
| L12 | Com o reranker ligado, o fuzzy, a reescrita, o multi-query e o HyDE não mudam o resultado, no `legal-ptbr` e no `legal-ptbr-v2`. Sem o reranker, no `legal-ptbr-v2`, o HyDE sobe o MRR de 0,740 para 0,788 e ajuda as perguntas coloquiais, e o fuzzy sobe para 0,783 e ajuda as formais. O multi-query piora. Cada técnica de LLM faz uma chamada ao LLM por busca, e ninguém mediu a latência nem o custo | Não há evidência para ligar uma dessas técnicas por padrão quando há um reranker. Sem reranker, o HyDE e o fuzzy valem como opção. O valor padrão continua `none` e `[dense, lexical]` | Decidido com a medida da tarefa 3.10 (2026-11-21): o padrão continua `none` e `[dense, lexical]`. Cada transformação acrescenta de 6 a 10 s ao p95 da busca e não muda a qualidade com o reranker |
| L13 | Medida em 2026-11-21. Cada busca com transformação chama o LLM da base. Com o `tencent/hy4-flash` pelo OpenRouter, o p95 da busca vai de 812 ms para 7,1 s (`rewrite`), 9,6 s (`hyde`) e 10,8 s (`multi_query`). O custo é de cerca de US$ 0,0001 por consulta. O `multi_query` pode piorar muito uma pergunta (com erros de digitação, a pergunta 2 passou da posição 1 para a 34) | Uma busca com transformação não cabe no RNF-01 nem no RNF-02 | Manter `none` como padrão (L12). Usar uma transformação só sem reranker e quando a latência de vários segundos for aceitável |
| L14 | O índice trigram é criado na primeira busca fuzzy e bloqueia escritas na tabela `chunks` enquanto a criação roda. O limiar de similaridade (0,5) é fixo no código. O fuzzy não ignora acentos na consulta | Em uma tabela grande, a primeira busca fuzzy bloqueia a ingestão. Um operador não ajusta o limiar | Criar o índice em um comando de operação (fase 4, tarefa 4.4). Ler o limiar da configuração da base quando houver um motivo medido |
| L15 | O embedding remoto da pergunta leva 787 ms no p95, e o reranker por API leva de 1,216 s a 1,435 s. O PostgreSQL leva de 13 a 21 ms | A busca na base real leva de 0,8 s (sem reranker) a 2,2 s (com reranker). O RNF-01 e o RNF-02 não cabem com provedor remoto | ADR-0020 (proposto): medir o RNF-01 sem o provedor de embeddings e mudar o RNF-02 para o reranker por API. Medir o reranker local em outra máquina |
| L16 | A busca lexical (`tsvector`) classifica todos os chunks que casam com a pergunta. O p95 cresce em linha reta com a base: 408 ms com 6 mil chunks e 7,939 s só da etapa lexical com 104 mil. O teste usa uma base sintética que repete 150 documentos | Com a configuração padrão, o RNF-01 e o RNF-03 falham em bases acima de poucos milhares de chunks | Em parte resolvida em 2026-11-21: o retriever `bm25` (tarefa 3.4) leva 60 ms de p95 com 102 mil chunks. O padrão continua `[dense, lexical]`, porque o `bm25` exige a imagem `vlade-postgres-bm25` (AGPL-3.0). Falta decidir se o `tsvector` deve parar de classificar todos os chunks que casam |
| L18 | O retriever `bm25` não usa a RLS: a busca roda na função `vlade_bm25_search()`, do papel `vlade_definer`, que lê o tenant de `app.tenant_id` (ADR-0022). O filtro de metadados não está no índice `bm25`. A primeira busca `bm25` cria o índice e bloqueia as escritas em `chunks` (cerca de 47 s com 102 mil chunks). Com erros de digitação, o Recall@10 do `bm25` é menor que o do `tsvector` (0,734 contra 0,807) | Um erro na função seria um vazamento entre tenants, sem a RLS como segunda barreira. Uma busca com filtro lê a linha de cada chunk que casa: cerca de 300 ms em uma consulta com 70 mil chunks que casam | O teste de isolamento do retriever confere a função. Criar o índice em um comando de operação (fase 4, tarefa 4.4). Pôr no índice as chaves de metadados mais usadas, quando houver uma medida de uso. Combinar `bm25` e `fuzzy` para as perguntas com erros |
| L19 | Ninguém mediu o ganho de qualidade das arestas condicionais do LangGraph. O limite `rewrite_below_score` depende da escala da pontuação (RRF ou reranker) | Não há um valor recomendado para os dois limites. As duas arestas ficam desligadas por padrão | Medir com um LLM real e um dataset com perguntas sem fundamento, na tarefa 3.7 (RAGAS) |
| L20 | O gate usa o backend em memória e embeddings `hashing` (ADR-0024). Ele não testa os índices do PostgreSQL, o reranker nem as transformações com LLM | Uma regressão só do `tsvector`, do `pg_trgm` ou do `pg_search` passa pelo gate. Os testes de integração cobrem esses adapters | Rodar o gate também com o PostgreSQL, se um erro de adapter passar pelo gate |
| L21 | A avaliação com RAGAS depende de um LLM juiz pago. O juiz erra: uma nota 0,0 apareceu numa resposta correta. Cada configuração rodou uma vez só | No `legal-ptbr` (20 perguntas), uma pergunta muda a faithfulness média em 0,05. A comparação vale só com o mesmo juiz. Uma medida de 109 perguntas custa cerca de US$ 0,50 | Conferir à mão uma amostra das notas do juiz. Repetir a medida para ver a variação |
| L22 | O Arize Phoenix substitui o Langfuse, mas os prompts continuam no `BuiltinPromptRegistry`. Ninguém usa o registro de prompts do Phoenix. O servidor Phoenix usa a Elastic License 2.0 | Um prompt novo exige uma versão nova do pacote. O Phoenix não pode ser oferecido como serviço gerenciado | Avaliar o registro de prompts do Phoenix ou a volta do Langfuse quando houver uma máquina com mais memória (ADR-0026) |
| L23 | O download de `source_uri` por `https://` resolve o nome e bloqueia endereços privados antes da requisição. O cliente HTTP resolve o nome de novo. Uma troca de DNS entre as duas etapas não é detectada. Sem `VLADE_SOURCES__ALLOWED_DOMAINS`, o download por URL fica desligado | Um servidor com DNS sob controle de um atacante pode receber um endereço privado na segunda resolução. O bloqueio por lista não protege contra nome público que muda de dono | Fixar o endereço resolvido na conexão do cliente HTTP. Até lá, usar apenas domínios de confiança na lista |
| L17 | Cada documento custa 62 transações na ingestão. Um documento de 1 página rende de 8 a 15 páginas por segundo, e um de 100 páginas rende de 56 a 70 | O RNF-04 só vale para documentos longos | ADR-0020 (proposto): gravar os passos do job em uma só transação, agrupar as escritas e evitar leituras repetidas. Medir de novo depois |

### Fase 4 — Operação

| # | Tarefa | Referência |
|---|---|---|
| 4.1 | Flows Kestra: `ingest_batch`, `reindex_knowledge_base`, `evaluate_nightly`, `backup` | ARCHITECTURE §12.2, ADR-0011 · Concluída em 2026-11-22: quatro flows em `deploy/kestra/flows/`, com `RunEvaluation`, `POST /v1/evaluations`, job `evaluation` e a ferramenta MCP `vlade_evaluate`. O registro de datasets lê `VLADE_EVALUATION__DATASETS_PATH`. Os gatilhos diários começam desligados. A aceitação de reindexação sob carga roda no teste de carga da tarefa 4.2, sem servidor Kestra no perfil `dev` |
| 4.2 | Reindexação sem parada nos modos `embeddings` e `full` | ARCHITECTURE §13, ADR-0027 · Concluída em 2026-11-21: `ReindexKnowledgeBase` (prévia, `confirm` e `conflict`), job `reindex` no worker, `POST /v1/knowledge-bases/{kb}/reindex` e `vlade-rag reindex`. A troca de espaço e a publicação de uma versão usam a mesma trava da base, então nenhuma busca mistura espaços. Os testes cobrem um documento publicado durante a construção, uma publicação depois da troca e uma reindexação com buscas e ingestões em paralelo, nos dois modos. Um job repetido não cria versões duplicadas. A limpeza do espaço antigo fica para a tarefa 4.4 |
| 4.3 | Ferramentas MCP de escrita com confirmação | MCP_SPEC §5.7 a §5.10 · Concluída em 2026-11-21 para §5.7 a §5.9: `vlade_ingest_document` (texto ou `source_uri`), `vlade_delete_document` e `vlade_reindex_knowledge_base`. As ferramentas ficam fora de `tools/list` até `tenants.settings.mcp.write_tools_enabled` ser `true`. Prévia sem `confirm`, papel mínimo `writer` e `admin`, limite por grupo e auditoria com o id do evento. O download por `https://` exige uma lista de domínios permitidos. A ferramenta `vlade_evaluate` (§5.10) depende do caso de uso `RunEvaluation` da tarefa 4.1 |
| 4.4 | Módulo `ops`: recuperação de jobs vencidos, limpeza de versões antigas, health checks | ARCHITECTURE §10 · Concluída em 2026-11-21: `vlade-rag ops cleanup`, `recover-jobs` e `health`. A limpeza apaga espaços `retired` e `building` órfãos e versões `superseded` depois do período de espera |
| 4.5 | Grafana Alloy, Prometheus, Loki, Tempo e Grafana no perfil `prod` | ADR-0015 · Concluída em 2026-11-22: Alloy, Prometheus, Loki, Tempo, Grafana e os exporters `node-exporter`, `cadvisor`, `postgres-exporter` e `redis-exporter` em `deploy/observability/`. O Alloy recebe OTLP, escreve métricas no Prometheus, envia traces ao Tempo e lê os logs do Docker para o Loki. O Grafana provisiona as fontes de dados e todas as portas escutam em `127.0.0.1`. O Alloy também roda no perfil `staging`, apontado para backends externos. Um teste de fumaça enviou uma métrica e um trace ao Alloy e leu os dois nos backends |
| 4.6 | Cinco dashboards e alertas | VLADE-RAG §14 · Concluída em 2026-11-23: cinco dashboards provisionados no Grafana (`rag-performance`, `llm-observability`, `retrieval-analytics`, `infrastructure` e `workflow-monitoring`), alimentados pelo catálogo de métricas da arquitetura §16.2. Oito alertas em `deploy/observability/prometheus/rules/alerts.yml`, cada um com um teste de falha provocada em `tests/promtool/alerts.test.yml`, executado pela CI. `scripts/observability/seed_telemetry.py` gera dados reais sem provedor externo |
| 4.7 | Guia de implantação em `docs/operacao/` | — · Concluída em 2026-11-23: `docs/operacao/implantacao.md` cobre pré-requisitos, variáveis de ambiente, perfis, instalação, verificação, configuração inicial, observabilidade, operação diária, atualização, backup, segurança e solução de problemas. O linter de documentação passou a ler a pasta |

**Critérios de aceite:**

- Uma reindexação completa roda pelo Kestra enquanto um teste de carga faz consultas. Nenhuma consulta falha. Nenhuma consulta mistura espaços de embeddings. Os flows estão em `deploy/kestra/flows/`. O servidor Kestra não faz parte do perfil `dev`: a parte de concorrência é coberta por `tests/integration/test_reindex_load.py`, e a estrutura dos flows por `tests/unit/test_kestra_flows.py`.
- Os cinco dashboards mostram dados reais.
- Cada alerta dispara em um teste de falha provocada.

**Resultado (2026-11-23):** a reindexação com carga rodou em `tests/integration/test_reindex_load.py`, nos modos `embeddings` e `full`, sem falha de consulta e sem mistura de espaços. O script `scripts/observability/seed_telemetry.py` gerou dados reais e os cinco dashboards trouxeram resultados no Grafana. Os oito alertas dispararam em `tests/promtool/alerts.test.yml`, que a CI executa. O PR #31 encerrou a fase com 13 jobs verdes.

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
