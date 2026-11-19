# Vlade-RAG — Especificação do projeto

> Versão 1.0 — 2026-11-19
> Fonte: [`VLADE-RAG.md`](../VLADE-RAG.md). Se este documento e o `VLADE-RAG.md` se contradizem, o `VLADE-RAG.md` vale.
> Documentos relacionados: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`MCP_SPEC.md`](MCP_SPEC.md), [`ROADMAP.md`](ROADMAP.md), [`adr/`](adr/README.md).

---

## 1. Objetivo

O Vlade-RAG é um framework open source de Retrieval-Augmented Generation (RAG), com licença MIT. O framework entrega um núcleo reutilizável para ingestão, indexação, recuperação, geração e avaliação. Uma aplicação nova usa esse núcleo e não reimplementa o pipeline RAG.

O framework troca componentes por configuração: provedor de LLM, modelo de embeddings, reranker, banco vetorial, estratégia de chunking, estratégia de recuperação e fonte de documentos.

## 2. Escopo

### 2.1. Dentro do escopo

- Biblioteca Python `vlade-rag`, com núcleo, ports e adapters.
- Motor Rust `vlade-rag-core` para funções de CPU, com implementação de reserva em Python.
- API REST (FastAPI).
- Servidor MCP para qualquer cliente MCP.
- CLI `vlade-rag`.
- Worker de ingestão.
- Fluxo de consulta linear e fluxo de consulta em LangGraph.
- Flows Kestra para operação.
- Avaliação com métricas de recuperação e RAGAS.
- Observabilidade com OpenTelemetry, Langfuse e a stack LGTM.
- Arquivos Docker Compose com os perfis `dev`, `staging` e `prod`.
- Agent Skill `skills/vlade-rag/` para clientes MCP.

### 2.2. Fora do escopo

- Interface gráfica de chat para usuário final.
- Treinamento ou fine-tuning de modelos.
- Provedor de identidade próprio.
- Orquestrador de workflows próprio.
- Human-in-the-loop no fluxo de consulta da versão 1 (ADR-0014).

## 3. Atores

| Ator | Descrição |
|---|---|
| **Desenvolvedor integrador** | Usa o Vlade-RAG como biblioteca ou como serviço em uma aplicação própria. |
| **Operador** | Implanta, monitora e mantém o Vlade-RAG. Usa Kestra, Grafana e Langfuse. |
| **Administrador de tenant** | Gerencia as bases de conhecimento, os documentos e as chaves de API de um tenant. |
| **Usuário final** | Faz perguntas por uma aplicação cliente. O usuário final não acessa o Vlade-RAG diretamente. |
| **Agente de IA** | Um cliente MCP, por exemplo Claude Code ou Hermes Agent. O agente consulta as bases pelo servidor MCP. |
| **Contribuidor** | Pessoa que envia código ou documentação ao projeto open source. |

## 4. Casos de uso

| ID | Caso de uso | Ator principal | Interfaces |
|---|---|---|---|
| UC-01 | Criar uma base de conhecimento | Administrador de tenant | API, CLI |
| UC-02 | Ingerir um documento | Administrador de tenant, Agente de IA | API, CLI, MCP |
| UC-03 | Ingerir um lote de documentos | Operador | Kestra, CLI |
| UC-04 | Consultar o estado de uma ingestão | Administrador de tenant, Agente de IA | API, CLI, MCP |
| UC-05 | Buscar trechos relevantes (`search`) | Desenvolvedor integrador, Agente de IA | API, MCP, biblioteca |
| UC-06 | Obter uma resposta com citações (`query`) | Desenvolvedor integrador, Agente de IA | API, MCP, biblioteca |
| UC-07 | Ler um documento e os metadados do documento | Agente de IA | API, MCP |
| UC-08 | Apagar um documento | Administrador de tenant | API, CLI, MCP |
| UC-09 | Reindexar uma base de conhecimento | Operador | Kestra, API, MCP |
| UC-10 | Sincronizar uma fonte externa | Operador | Kestra |
| UC-11 | Avaliar a qualidade de uma base | Operador | Kestra, CLI, MCP |
| UC-12 | Trocar um componente por configuração | Desenvolvedor integrador | Configuração |
| UC-13 | Acrescentar um adapter por plugin | Desenvolvedor integrador, Contribuidor | Entry point Python |
| UC-14 | Monitorar o sistema | Operador | Grafana, Langfuse |

## 5. Requisitos funcionais

### 5.1. Tenants e bases de conhecimento

| ID | Requisito |
|---|---|
| RF-01 | O sistema deve isolar os dados de cada tenant. |
| RF-02 | Um tenant pode ter várias bases de conhecimento. |
| RF-03 | Cada base de conhecimento deve ter configuração própria de idioma, chunking, embeddings, recuperação e geração. |
| RF-04 | Cada base de conhecimento deve apontar para um espaço de embeddings ativo. |

### 5.2. Ingestão

| ID | Requisito |
|---|---|
| RF-10 | O sistema deve aceitar texto puro, Markdown, HTML, PDF e DOCX na versão 1. |
| RF-11 | O sistema deve guardar o arquivo original no armazenamento de objetos. |
| RF-12 | O sistema deve validar o tipo de arquivo, o tamanho máximo e a cota do tenant antes de processar. |
| RF-13 | Se o hash do conteúdo novo é igual ao hash da versão publicada, o sistema não deve reprocessar o documento. |
| RF-14 | Uma atualização de documento deve criar uma versão nova. |
| RF-15 | O sistema deve publicar uma versão nova de forma atômica. Uma consulta não deve ver uma versão indexada pela metade. |
| RF-16 | Cada ingestão deve gerar um job com estado consultável: `pending`, `running`, `succeeded`, `failed`, `cancelled`. |
| RF-17 | Cada etapa do pipeline de ingestão deve ser idempotente. |
| RF-18 | O sistema deve gerar embeddings em lotes de tamanho configurável e respeitar o limite de requisições do provedor. |

### 5.3. Recuperação

| ID | Requisito |
|---|---|
| RF-20 | O sistema deve oferecer recuperação densa (pgvector) e recuperação léxica (`tsvector`). |
| RF-21 | O sistema pode oferecer recuperação fuzzy (`pg_trgm`) e BM25 (`pg_search`) por configuração. |
| RF-22 | O sistema deve combinar os resultados dos retrievers com RRF. O valor padrão de `k` é 60. |
| RF-23 | O sistema deve aceitar filtros por metadados do documento. |
| RF-24 | O sistema pode aplicar reranking por configuração. |
| RF-25 | O sistema pode transformar a consulta por configuração: reescrita, multi-query, HyDE. |
| RF-26 | A busca léxica em português deve ignorar acentos. |

### 5.4. Geração

| ID | Requisito |
|---|---|
| RF-30 | A resposta deve conter uma lista de citações. Cada citação contém `document_id`, `chunk_id`, título do documento e posição no documento. |
| RF-31 | Se o contexto não sustenta uma resposta, o sistema deve responder que não encontrou a informação nas fontes. |
| RF-32 | O prompt de geração deve separar as instruções do sistema e o conteúdo recuperado. |
| RF-33 | A API deve oferecer resposta em streaming para o modo `query`. |
| RF-34 | O sistema deve ter prompts padrão em português do Brasil e em inglês. |
| RF-35 | Os prompts devem ter versão. A resposta deve informar a versão do prompt usado. |

### 5.5. Exclusão e LGPD

| ID | Requisito |
|---|---|
| RF-40 | A exclusão de um documento deve apagar as versões, os chunks, os vetores, as entradas de cache e o arquivo original. |
| RF-41 | A exclusão de um tenant deve apagar todos os dados do tenant. |
| RF-42 | O registro de consultas deve guardar o hash da consulta por padrão. A configuração do tenant pode ativar o registro do texto da consulta. |

### 5.6. Interfaces

| ID | Requisito |
|---|---|
| RF-50 | A API REST deve expor os casos de uso UC-01 a UC-09 e UC-11. |
| RF-51 | O servidor MCP deve seguir o [`MCP_SPEC.md`](MCP_SPEC.md). |
| RF-52 | A CLI deve expor os casos de uso UC-01 a UC-06, UC-08, UC-09 e UC-11. |
| RF-53 | Uma aplicação Python deve conseguir usar os casos de uso sem instalar FastAPI, MCP, LangGraph ou Kestra. |

### 5.7. Extensibilidade

| ID | Requisito |
|---|---|
| RF-60 | A configuração deve escolher cada adapter pelo nome. |
| RF-61 | Um pacote externo deve conseguir registrar um adapter pelo grupo de entry points `vlade_rag.plugins`. |
| RF-62 | Cada port deve ter uma suíte de testes de contrato publicada no pacote. Um plugin externo deve conseguir rodar essa suíte. |

### 5.8. Avaliação

| ID | Requisito |
|---|---|
| RF-70 | O sistema deve calcular Recall@K, Precision@K, MRR e NDCG sem LLM. |
| RF-71 | O sistema deve calcular faithfulness, answer relevancy, context precision e context recall com RAGAS. |
| RF-72 | Cada relatório de avaliação deve registrar a configuração completa usada. |
| RF-73 | A CI deve falhar se uma métrica de recuperação cai mais que o limite configurado. |

## 6. Requisitos não funcionais

As metas abaixo são as metas da versão 1. O benchmark da fase 3 valida as metas de latência e de vazão. Se o benchmark mostra que uma meta não é realista, um ADR muda a meta.

| ID | Requisito | Meta v1 | Como medir |
|---|---|---|---|
| RNF-01 | Latência p95 de `search`, sem reranking, base com 1 milhão de chunks | ≤ 300 ms | Benchmark com `k6` no perfil `staging` |
| RNF-02 | Latência p95 de `search`, com reranking de 50 candidatos | ≤ 1 s | Benchmark com `k6` |
| RNF-03 | Tempo até o primeiro token em `query` com streaming, sem o tempo do LLM remoto | ≤ 1,5 s | Spans OpenTelemetry |
| RNF-04 | Vazão de ingestão por worker, sem o tempo de embeddings | ≥ 50 páginas por segundo | Benchmark de ingestão |
| RNF-05 | Cobertura de testes dos módulos `core`, `retrieval` e `ingestion` | ≥ 85% | `pytest --cov` na CI |
| RNF-06 | Disponibilidade da API em produção | ≥ 99,5% por mês | Prometheus |
| RNF-07 | Vazamento de dados entre tenants | Zero | Teste de isolamento na CI |
| RNF-08 | Licenças das dependências do núcleo | Só licenças permissivas (ADR-0001) | Verificação de licenças na CI |
| RNF-09 | Plataformas com wheel do motor Rust | Linux x86_64 e aarch64, macOS x86_64 e arm64, Windows x86_64 | CI de release |
| RNF-10 | Versões de Python | 3.12 e 3.13 | Matriz da CI |
| RNF-11 | Memória do perfil `dev` | ≤ 3 GB de RAM, sem o Ollama | `docker stats` |

## 7. Restrições

- O ambiente de desenvolvimento é um notebook com 8 GB de RAM.
- O código e os identificadores usam inglês. A documentação usa português do Brasil.
- A documentação passa no linter da skill `asd-ste100-pt-br` sem violações duras.
- O núcleo usa só dependências com licença permissiva (ADR-0001).

## 8. Critérios de sucesso da versão 1

1. Um desenvolvedor instala o pacote e ingere uma pasta de documentos com menos de 10 linhas de código Python.
2. Um agente MCP consulta uma base e recebe respostas com citações corretas.
3. O teste de isolamento entre tenants passa em todas as interfaces.
4. A troca do provedor de LLM e do modelo de embeddings exige só uma mudança de configuração e uma reindexação.
5. Os cinco dashboards mostram dados reais no perfil `prod`.

## 9. Glossário

O glossário oficial está na seção 2 do [`VLADE-RAG.md`](../VLADE-RAG.md#2-glossário).
