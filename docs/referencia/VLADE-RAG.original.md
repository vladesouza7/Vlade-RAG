Criar um projeto Sistema RAG de nível de produção. que possa ser usado como base caso queira usar em outros projetos como se fosse um framework RAG.
Ou seja desenvolver um projeto chamado Vlade-RAG, concebido não apenas como um chatbot com RAG, mas como um framework de Retrieval-Augmented Generation (RAG) modular, extensível e preparado para produção.

A ideia é construir um núcleo independente que possa ser reutilizado em diferentes aplicações, sem precisar implementar novamente todo o pipeline de ingestão, processamento, indexação, recuperação e geração de respostas.

Pensei nele como uma infraestrutura de RAG que poderá atender projetos como:
- Assistentes inteligentes para atendimento.
- Chatbots especializados em vendas.
- Sistemas de consulta a documentos empresariais.
- Assistentes jurídicos e administrativos.
- Bases de conhecimento corporativas.
- Agentes de IA com acesso a documentos e informações internas.
- Sistemas multi-tenant, nos quais diferentes empresas possuem suas próprias bases de conhecimento.

1. Visão geral do projeto
Nome: Vlade-RAG
Categoria: RAG Framework / AI Infrastructure
Linguagem principal: Rust, Python
Arquitetura: Modular, desacoplada e orientada a interfaces.

O objetivo é separar cinco responsabilidades fundamentais:
1. Ingestion: receber e processar documentos.
2. Knowledge: armazenar, organizar e indexar conhecimento.
3. Retrieval: recuperar informações relevantes.
4. Generation: produzir respostas fundamentadas nas fontes.
5. Evaluation: avaliar a qualidade e a confiabilidade dos resultados.
O diferencial será permitir trocar componentes sem precisar reescrever a aplicação.

Por exemplo:
- Trocar Ollama por OpenAI, Gemini ou OpenRouter.
- Trocar PostgreSQL/pgvector por Qdrant.
- Trocar o mecanismo de embeddings.
- Trocar o modelo de reranking.
- Trocar a estratégia de chunking.
- Adicionar novas fontes de documentos.
- Utilizar diferentes estratégias de recuperação.


Pensei como proposta de arquitetura
Usando seguintes princípios:
1. Clean Architecture: separar domínio, infraestrutura e aplicação.
2. SOLID: componentes com responsabilidades bem definidas.
3. Dependency Injection: injetar provedores e implementações.
4. Adapter Pattern: abstrair bancos, embeddings e LLMs.
5. Factory Pattern: facilitar a instanciação de componentes.
6. Plugin Architecture: permitir adicionar novos provedores.
7. 12-Factor App: configurações externas, logs, processos e portabilidade.
8. Test-Driven Development: testes unitários, integração e avaliação.

Para o **Vlade-RAG**, eu recomendo utilizar uma arquitetura de observabilidade em camadas, combinando ferramentas especializadas em IA, infraestrutura e execução de workflows.

E sobre o **Kestra**, considero uma excelente adição ao projeto. Inclusive, vejo uma oportunidade interessante: utilizar o Kestra para orquestrar processos de ingestão, sincronização e manutenção das bases de conhecimento, enquanto o LangGraph controla o fluxo inteligente de execução do RAG.

Minha recomendação principal seria:

- **Langfuse:** observabilidade de LLMs e RAG.
- **OpenTelemetry:** instrumentação e padronização de telemetria.
- **Prometheus:** métricas.
- **Grafana:** dashboards.
- **Loki:** logs.
- **Tempo:** rastreamento distribuído.
- **Kestra:** orquestração de workflows e pipelines operacionais.

Não são ferramentas concorrentes. Cada uma resolve um problema diferente.

# 1. Arquitetura de observabilidade do Vlade-RAG



Eu dividiria a observabilidade em três domínios:

| Domínio | Ferramenta | O que monitorar |
|---|---|---|
| AI Observability | Langfuse | LLM, prompts, tokens, RAG e avaliações |
| Application Observability | OpenTelemetry | Traces, métricas e instrumentação |
| Infrastructure Observability | Prometheus, Grafana, Loki e Tempo | CPU, memória, logs, latência e disponibilidade |

Isso permite investigar tanto problemas de infraestrutura quanto problemas de qualidade das respostas.

## 1.1. Langfuse — inteligência artificial



Langfuse seria minha primeira escolha para o Vlade-RAG.

Ele permite acompanhar:

- Qual modelo foi utilizado.
- Qual prompt foi enviado.
- Quantos tokens foram consumidos.
- Tempo de resposta do LLM.
- Documentos recuperados.
- Etapas do pipeline RAG.
- Versões de prompts.
- Resultados das avaliações.
- Custos por modelo e execução.

Também permite trabalhar com datasets e experimentos para comparar versões do RAG. [Langfuse](https://langfuse.com/integrations?utm_source=chatgpt.com)

**Exemplo de rastreamento:**

```text
Trace: rag_query
│
├── query_analysis
│
├── query_rewriting
│
├── hybrid_retrieval
│   ├── pgvector
│   ├── pg_search
│   └── pg_trgm
│
├── rrf_fusion
│
├── reranking
│
├── context_assembly
│
├── llm_generation
│
└── response
```

Com isso, podemos identificar exatamente onde uma consulta está demorando ou perdendo qualidade.

Documentação: [Langfuse](https://langfuse.com/docs?utm_source=chatgpt.com).

## 1.2. OpenTelemetry — padrão de instrumentação

OpenTelemetry seria obrigatório na arquitetura.

Ele não é propriamente um dashboard ou banco de observabilidade. É o padrão para instrumentar aplicações e transmitir telemetria.

No Vlade-RAG, utilizaria para:

- Tracing distribuído.
- Métricas.
- Logs.
- Correlação entre serviços.
- Instrumentação Python.
- Instrumentação Rust.

Exemplo:

```text
FastAPI
   |
   v
OpenTelemetry
   |
   +----> Langfuse
   |
   +----> Grafana Stack
   |
   +----> Alerting
```

Uma vantagem é não ficar preso a um fornecedor específico.

## 1.3. Grafana Stack — infraestrutura e aplicações

Minha escolha seria:

| Ferramenta | Responsabilidade |
|---|---|
| Prometheus | Coleta de métricas |
| Grafana | Dashboards |
| Loki | Centralização de logs |
| Tempo | Tracing distribuído |
| Grafana Alloy | Coleta e encaminhamento de telemetria |

O Tempo permite relacionar traces, logs e métricas, facilitando a investigação de problemas entre serviços. [Grafana Labs](https://grafana.com/docs/tempo/latest/?utm_source=chatgpt.com)

Eu utilizaria Grafana Alloy como coletor, em vez de iniciar uma implementação nova com Grafana Agent, que já chegou ao fim de vida. [Grafana Labs](https://grafana.com/docs/agent/latest/flow/tasks/opentelemetry-to-lgtm-stack/?utm_source=chatgpt.com)

Documentação: [Grafana Observability](https://grafana.com/docs/?utm_source=chatgpt.com).

---

# 2. E o Kestra? Onde ele entra?



Kestra é uma escolha muito interessante para o Vlade-RAG.

Eu o utilizaria como **Workflow Orchestrator**, responsável por coordenar processos operacionais e pipelines de dados.

O Kestra trabalha com workflows declarativos em YAML, integrações, agendamentos, eventos, execução de scripts e tratamento de falhas. Também oferece visualização de execuções, logs e métricas. [kestra.io](https://kestra.io/docs/use-cases/data-pipelines?utm_source=chatgpt.com)

### Onde utilizar no Vlade-RAG?

| Processo | Utilização do Kestra |
|---|---|
| Ingestion Pipeline | Coordenar ingestão |
| Document Processing | Executar processamento |
| Batch Embeddings | Gerar embeddings em lotes |
| Knowledge Sync | Sincronizar bases |
| Reindexing | Reindexar documentos |
| Document Updates | Atualizar documentos |
| Data Validation | Validar dados |
| Evaluation Pipeline | Executar avaliações RAGAS |
| Regression Tests | Comparar versões do RAG |
| Backup | Coordenar backups |
| Scheduled Jobs | Executar rotinas agendadas |

### Exemplo de workflow

Imagine que um usuário envie 500 documentos para uma base de conhecimento.

O Kestra poderá controlar:

```text
                 DOCUMENT UPLOAD
                        |
                        v
                 VALIDATE FILES
                        |
                        v
                 EXTRACT CONTENT
                        |
                        v
                  CLEAN CONTENT
                        |
                        v
                   CHUNKING
                        |
                        v
                GENERATE EMBEDDINGS
                        |
                        v
                 VECTOR INDEXING
                        |
                        v
                 FULLTEXT INDEXING
                        |
                        v
                 VALIDATE INDEXES
                        |
                        v
                  RAG EVALUATION
                        |
                        v
                 PUBLISH KNOWLEDGE
```

Cada etapa poderá ter:

- Logs.
- Retentativas.
- Timeout.
- Controle de concorrência.
- Tratamento de falhas.
- Histórico de execução.

Isso é particularmente interessante para processos que podem levar minutos ou horas.

---

# 3. Kestra versus LangGraph

Essa é uma distinção arquitetural muito importante.

Eu utilizaria os dois, mas com responsabilidades diferentes.

| Característica | Kestra | LangGraph |
|---|---|---|
| Finalidade | Orquestração operacional | Orquestração inteligente |
| Linguagem | YAML / tarefas | Python |
| Workflows | ETL, pipelines e automações | Fluxos de agentes e RAG |
| Execução | Agendada, eventos e API | Sob demanda e estado do grafo |
| Retentativas | Nativas | Controladas pelo grafo |
| Processamento em lote | Excelente aplicação | Possível, mas não é seu foco principal |
| Decisões com LLM | Por integração | Nativo ao ecossistema |
| Human-in-the-loop | Por workflows | Suporte a interrupções e retomadas |
| Avaliação RAG | Coordena avaliações | Pode participar do fluxo |
| Monitoramento | Execuções e tarefas | Estado e etapas do grafo |

### Minha arquitetura recomendada

```text
                    VLADE-RAG
                        |
          +-------------+-------------+
          |                           |
          v                           v
        KESTRA                     LANGGRAPH
   Operational Flows             AI Workflows
          |                           |
          v                           v
   Ingestion Pipeline           Query Processing
   Batch Embeddings             Query Rewriting
   Reindexing                   Hybrid Retrieval
   Knowledge Sync               Reranking
   RAGAS Evaluation             LLM Generation
   Backup                       Response Validation
          |                           |
          +-------------+-------------+
                        |
                        v
                  VLADE-RAG CORE
                        |
                        v
                   RUST ENGINE
                        |
                        v
                   POSTGRESQL
```

**Uma regra que estabeleceria:**

- Kestra decide quando e como executar processos operacionais.
- LangGraph decide como conduzir o raciocínio e a recuperação de informações.
- Vlade-RAG Core disponibiliza os componentes e contratos utilizados pelos dois.

Não colocaria Kestra no caminho de cada pergunta enviada ao chatbot. Isso adicionaria uma camada operacional desnecessária à latência de uma consulta síncrona.

# 4. Kestra também possui observabilidade própria

Outro ponto positivo: o Kestra não depende exclusivamente do Grafana para monitorar seus workflows.

Ele possui interface própria para acompanhar:

- Execuções.
- Status das tarefas.
- Logs.
- Inputs e outputs.
- Histórico.
- Dependências.
- Falhas e retentativas.
- Métricas de execução.

Além disso, sua arquitetura disponibiliza endpoints Prometheus e traces OpenTelemetry. Portanto, podemos integrar os dados do Kestra à infraestrutura central de observabilidade. [kestra.io](https://kestra.io/docs/architecture?utm_source=chatgpt.com)

Documentação: [Kestra Architecture](https://kestra.io/docs/architecture?utm_source=chatgpt.com).

# 5. Kestra ou Celery?

Aqui faria uma alteração na arquitetura que propusemos anteriormente.

Inicialmente tínhamos Celery + Redis. Com a entrada do Kestra, precisamos avaliar se realmente necessitamos dos dois.

Minha recomendação:

| Necessidade | Escolha |
|---|---|
| Orquestração de pipelines | Kestra |
| Ingestão de documentos em lote | Kestra |
| Sincronização de conhecimento | Kestra |
| Reindexação | Kestra |
| Avaliações RAGAS agendadas | Kestra |
| Processamento assíncrono simples | Redis + worker, se necessário |
| Raciocínio de agentes | LangGraph |

**Eu não colocaria Celery na primeira versão.**

Kestra já oferece recursos de execução, filas, workers, retries e controle de workflows. Manter Celery simultaneamente desde o início aumentaria a complexidade operacional.

Se futuramente identificarmos uma necessidade específica de processamento de tarefas de alta frequência, podemos avaliar sua inclusão.

# 6. Arquitetura final de observabilidade

Esta seria minha proposta oficial:

```text
                     VLADE-RAG
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       Python           Rust           Kestra
          |              |              |
          +--------------+--------------+
                         |
                         v
                  OpenTelemetry
                         |
                         v
                  Grafana Alloy
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
      Prometheus       Loki           Tempo
          |              |              |
          +--------------+--------------+
                         |
                         v
                      Grafana

                         +

                      Langfuse
                (AI Observability)
```

O Langfuse terá seu próprio armazenamento e interface de análise de IA, mas receberá instrumentação integrada ao padrão OpenTelemetry.

## 6.1. O que monitorar?

Eu criaria cinco dashboards:

| Dashboard | Indicadores |
|---|---|
| RAG Performance | Latência, Recall@K, Precision@K, NDCG |
| LLM Observability | Tokens, custos, modelos e erros |
| Retrieval Analytics | pgvector, BM25, RRF e Reranking |
| Infrastructure | CPU, RAM, PostgreSQL, Redis e MinIO |
| Workflow Monitoring | Kestra, ingestões, falhas e reprocessamentos |

Também criaria alertas para:

- Falhas consecutivas na ingestão.
- Aumento da latência de recuperação.
- Erros de geração.
- Falhas de conexão com provedores.
- Crescimento de filas.
- Indisponibilidade do PostgreSQL.
- Consumo excessivo de memória.
- Queda na qualidade das avaliações.

---

# 7. Stack tecnológica consolidada do Vlade-RAG

Com essas decisões, nossa arquitetura fica assim:

| Camada | Tecnologia |
|---|---|
| Core | Rust + Python |
| Rust Binding | PyO3 + Maturin |
| API | FastAPI |
| Orquestração AI | LangGraph |
| Workflow Orchestration | Kestra |
| RAG Evaluation | RAGAS |
| AI Observability | Langfuse |
| Telemetry | OpenTelemetry |
| Collector | Grafana Alloy |
| Metrics | Prometheus |
| Dashboards | Grafana |
| Logs | Loki |
| Distributed Tracing | Tempo |
| Database | PostgreSQL |
| Vector Search | pgvector |
| BM25 | pg_search |
| Full Text Search | tsvector |
| Fuzzy Search | pg_trgm |
| Normalization | unaccent |
| Fusion | RRF |
| Reranking | BGE / Cross-Encoder |
| Embeddings | Sentence Transformers / Ollama |
| LLM | Ollama / OpenAI / Gemini / OpenRouter |
| Cache | Redis |
| Object Storage | MinIO |
| Containers | Docker |

## 8. Uma recomendação para o seu ambiente

Como você pretende desenvolver isso também no seu HomeLab, faria três perfis:

**Development — mínimo**

- Vlade-RAG API.
- PostgreSQL + pgvector.
- Redis.
- Ollama externo ou provedor remoto.
- Langfuse Cloud ou desativado.

**Staging — integração**

- Kestra.
- LangGraph.
- RAGAS.
- Langfuse.
- PostgreSQL.
- MinIO.
- OpenTelemetry.

**Production — completo**

- Todos os componentes.
- Grafana.
- Prometheus.
- Loki.
- Tempo.
- Grafana Alloy.
- Kestra com workers dimensionados.
- Langfuse self-hosted ou Cloud.

Não executaria a stack completa no notebook de 8 GB simultaneamente. A separação por perfis permitirá desenvolver sem sobrecarregar o equipamento.

---

# 9. Minha decisão arquitetural

Eu consolidaria três pilares para o Vlade-RAG:

| Pilar | Responsável | Objetivo |
|---|---|---|
| Intelligence | LangGraph + LLM + RAGAS | Recuperar, raciocinar e avaliar |
| Orchestration | Kestra | Automatizar e coordenar processos |
| Observability | Langfuse + OpenTelemetry + Grafana | Monitorar e melhorar continuamente |

**Uma última sugestão:** incluir um módulo chamado `vlade-rag-ops`.

Ele seria responsável por disponibilizar integrações operacionais para Kestra, observabilidade, health checks, métricas, auditoria e manutenção.

Assim, o framework não será apenas um mecanismo de RAG, mas uma infraestrutura completa para construir, executar, monitorar e avaliar aplicações baseadas em conhecimento.

Minha escolha seria manter **Kestra + LangGraph + Langfuse + OpenTelemetry + Grafana Stack** como arquitetura oficial do Vlade-RAG.


Perfeito. Vamos estabelecer isso como uma **decisão arquitetural oficial do Vlade-RAG**.

Além de Kestra, LangGraph, Langfuse e LGTM, vamos incluir o **MCP (Model Context Protocol)** como parte da arquitetura de integração.

Considero essa inclusão muito importante porque permitirá que o Vlade-RAG não seja apenas consumido por aplicações Python e APIs REST, mas também por agentes inteligentes, IDEs e outros sistemas compatíveis com MCP.

# Vlade-RAG — Arquitetura oficial

**High-Performance Modular RAG Infrastructure**

Os cinco pilares serão:

| Pilar | Tecnologia | Responsabilidade |
|---|---|---|
| Core Engine | Rust + Python | Processamento e funcionalidades RAG |
| AI Orchestration | LangGraph | Orquestração inteligente |
| Workflow Orchestration | Kestra | Pipelines e automações |
| AI Observability | Langfuse | Rastreamento e avaliação de IA |
| Infrastructure Observability | LGTM | Logs, métricas e traces |
| Agent Integration | MCP | Integração com agentes e ferramentas |

# 1. Onde o MCP entra?

Minha proposta é criar um módulo próprio:

`vlade-rag-mcp`

Ele será uma camada de exposição das funcionalidades do framework por meio do Model Context Protocol.

Arquitetura:

```text
             AI AGENTS / MCP CLIENTS
                       |
                       v
                 MCP PROTOCOL
                       |
                       v
                VLADE-RAG-MCP
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Search       Ingestion    Knowledge
       Tools          Tools       Tools
          |            |            |
          +------------+------------+
                       |
                       v
                  VLADE-RAG CORE
                       |
          +------------+------------+
          |                         |
          v                         v
     LANGGRAPH                 RUST ENGINE
          |                         |
          +------------+------------+
                       |
                       v
                   POSTGRESQL
```

O MCP deverá disponibilizar três categorias:

- **Tools:** executar consultas, pesquisar documentos, consultar bases e iniciar operações autorizadas.
- **Resources:** disponibilizar documentos, metadados e informações de bases de conhecimento.
- **Prompts:** oferecer templates reutilizáveis para operações RAG.

Exemplos de ferramentas:

```text
vlade_rag.search
vlade_rag.query
vlade_rag.list_knowledge_bases
vlade_rag.get_document
vlade_rag.ingest_document
vlade_rag.get_ingestion_status
vlade_rag.evaluate
```

Uma distinção importante: operações de consulta poderão ser disponibilizadas diretamente, enquanto ingestão, exclusão e reindexação deverão exigir autorização e validação de permissões.

# 2. MCP nas ferramentas da arquitetura

Outro ponto interessante: não precisamos desenvolver todos os servidores MCP do zero. Algumas ferramentas já oferecem integração nativa.

| Componente | Integração MCP | Aplicação |
|---|---|---|
| Vlade-RAG | MCP Server próprio | Expor funcionalidades RAG |
| Kestra | MCP Server + Client | Executar e disponibilizar workflows |
| LangGraph | MCP Client/Adapters | Consumir ferramentas externas |
| Langfuse | MCP Server nativo | Consultar traces e avaliações |
| Grafana LGTM | Grafana MCP | Consultar métricas, logs e traces |

Algumas referências importantes:

- [Kestra MCP](https://kestra.io/docs/ai-orchestration/mcp-server?utm_source=chatgpt.com) — permite expor workflows como ferramentas e consumir servidores MCP externos. [kestra.io](https://kestra.io/docs/ai-orchestration/ai-agents?utm_source=chatgpt.com)
- [Langfuse MCP](https://langfuse.com/docs/api-and-data-platform/features/mcp-server?utm_source=chatgpt.com) — permite que agentes consultem dados de observabilidade.
- [Grafana MCP](https://grafana.com/docs/grafana/latest/ai-tools/mcp/?utm_source=chatgpt.com) — permite consultar Prometheus, Loki, Tempo, dashboards e alertas.
- [LangGraph MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters?utm_source=chatgpt.com) — permite incorporar ferramentas MCP aos grafos.

# 3. Atualização da arquitetura de diretórios

Incluiria o MCP como módulo independente:

```text
packages/
│
├── python/
│   └── vlade_rag/
│       │
│       ├── core/
│       ├── ingestion/
│       ├── embeddings/
│       ├── retrieval/
│       ├── reranking/
│       ├── generation/
│       │
│       ├── orchestration/
│       │   └── langgraph/
│       │
│       ├── evaluation/
│       │   └── ragas/
│       │
│       ├── mcp/
│       │   ├── server/
│       │   ├── tools/
│       │   ├── resources/
│       │   ├── prompts/
│       │   ├── auth/
│       │   └── policies/
│       │
│       ├── observability/
│       │   ├── langfuse/
│       │   └── opentelemetry/
│       │
│       └── integrations/
│           ├── kestra/
│           ├── grafana/
│           └── external/
│
└── rust/
    └── vlade_rag_core/
```

# 4. Segurança do MCP

Estabeleceria algumas regras desde a primeira versão:

1. Autenticação e autorização por usuário e tenant.
2. Controle de acesso individual por ferramenta.
3. Separação entre ferramentas de leitura e escrita.
4. Confirmação para operações destrutivas.
5. Auditoria das chamadas MCP.
6. Limitação de requisições.
7. Proteção contra exposição de documentos de outros tenants.
8. Nunca disponibilizar credenciais diretamente aos modelos.

Para começar, utilizaria ferramentas de leitura como padrão e habilitaria operações de escrita somente mediante permissões específicas.

---

# 5. Decisão final do projeto

Nossa arquitetura oficial fica consolidada:

| Pilar | Stack oficial |
|---|---|
| Core | Rust + Python |
| Database | PostgreSQL + pgvector |
| Hybrid Retrieval | pgvector + pg_search + tsvector + pg_trgm + unaccent |
| Fusion | RRF |
| Reranking | BGE / Cross-Encoder |
| AI Orchestration | LangGraph |
| Workflow Orchestration | Kestra |
| Evaluation | RAGAS |
| AI Observability | Langfuse |
| Infrastructure Observability | LGTM |
| Telemetry | OpenTelemetry |
| Agent Integration | MCP |
| Storage | MinIO |
| Cache | Redis |
| API | FastAPI |
| Deployment | Docker |

**Minha recomendação é considerar o MCP um recurso de primeira classe do Vlade-RAG, e não uma integração adicionada posteriormente.**

Isso permitirá que o framework seja utilizado por:

- Aplicações Python.
- APIs REST.
- Agentes LangGraph.
- Hermes Agent.
- Claude Code.
- IDEs compatíveis com MCP.
- Outros agentes que implementem o protocolo.

Assim, o Vlade-RAG poderá funcionar tanto como infraestrutura RAG para aplicações tradicionais quanto como provedor de conhecimento para ecossistemas de agentes de IA.

**Próxima entrega que considero essencial:** criar o `PROJECT_SPEC.md`, `ARCHITECTURE.md`, `MCP_SPEC.md` e `ROADMAP.md` como documentos fundadores do repositório Vlade-RAG. Eles serão a referência para implementação, testes e evolução do framework.