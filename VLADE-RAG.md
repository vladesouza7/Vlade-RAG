# Vlade-RAG — Prompt mestre de especificação

> Versão 2.2 — 2026-11-19. Documentos fundadores criados: veja a seção 22.
> Licença: MIT. O Vlade-RAG é um projeto open source.
> Origem: rascunho em [`docs/referencia/VLADE-RAG.original.md`](docs/referencia/VLADE-RAG.original.md).
> Leitor principal: um agente de IA que vai criar os documentos fundadores e implementar o framework.
> Leitor secundário: pessoas que vão manter ou usar o Vlade-RAG.

---

## 0. Como usar este documento

Este documento é o prompt de entrada do projeto. Ele define o que o Vlade-RAG é, como ele se organiza e em que ordem você constrói cada parte.

Siga estas regras, nesta ordem:

1. Leia o documento inteiro antes de criar qualquer arquivo.
2. Crie os documentos fundadores da seção 22. Escreva os documentos em português do Brasil. Use a skill `asd-ste100-pt-br` para revisar cada documento.
3. Registre cada decisão de arquitetura como um ADR em `docs/adr/`. Use o formato da seção 22.
4. Se você encontra uma decisão que este documento e os ADRs não respondem, registre um ADR com o status `Proposto` e pergunte ao usuário. Não implemente a parte afetada antes da resposta.
5. Implemente o projeto fase por fase, na ordem da seção 20. Não comece uma fase antes de a fase anterior cumprir os critérios de aceite.
6. No fim de cada fase, rode os testes e a avaliação. Relate o resultado real ao usuário, inclusive as falhas.
7. Se este documento e um documento fundador se contradizem, este documento vale. Corrija o documento fundador e informe o usuário.

As palavras **deve**, **não deve** e **pode** têm sentido fixo neste documento:

| Palavra | Sentido |
|---|---|
| **deve** | Requisito obrigatório. A implementação que não cumpre está errada. |
| **não deve** | Proibição. |
| **pode** | Permissão. A implementação escolhe. |
| **recomendado** | Escolha padrão. Você só muda com um ADR que explica o motivo. |

---

## 1. Objetivo

O Vlade-RAG é um **framework de Retrieval-Augmented Generation (RAG)** modular, extensível e preparado para produção. O Vlade-RAG não é um chatbot. O Vlade-RAG é open source, com licença MIT.

O Vlade-RAG entrega um núcleo reutilizável. Uma aplicação nova usa esse núcleo e não reimplementa ingestão, processamento, indexação, recuperação, geração e avaliação.

O diferencial do Vlade-RAG é a troca de componentes por configuração, sem reescrever a aplicação. Exemplos de troca:

- Trocar o provedor de LLM: Ollama, OpenAI, Gemini, OpenRouter.
- Trocar o banco vetorial: PostgreSQL com pgvector, Qdrant.
- Trocar o modelo de embeddings.
- Trocar o modelo de reranking.
- Trocar a estratégia de chunking.
- Acrescentar uma nova fonte de documentos.
- Trocar a estratégia de recuperação.

### 1.1. Aplicações que o Vlade-RAG atende

- Assistentes de atendimento.
- Chatbots de vendas.
- Sistemas de consulta a documentos de empresas.
- Assistentes jurídicos e administrativos.
- Bases de conhecimento corporativas.
- Agentes de IA com acesso a documentos internos.
- Sistemas multi-tenant, nos quais cada empresa tem bases de conhecimento próprias e isoladas.

### 1.2. Fora do escopo

O Vlade-RAG não entrega:

- Uma interface gráfica de chat para usuário final. Uma aplicação cliente faz essa interface.
- Treinamento ou fine-tuning de modelos.
- Um provedor de identidade próprio. O Vlade-RAG integra com um provedor externo.
- Um orquestrador de workflows próprio. O Kestra faz esse papel.

---

## 2. Glossário

Use estes termos sempre com o mesmo sentido. Não use sinônimos.

| Termo | Definição |
|---|---|
| **Tenant** | Uma organização cliente. Todo dado do sistema pertence a um tenant. |
| **Base de conhecimento** (`KnowledgeBase`) | Um conjunto de documentos de um tenant, com configuração própria de chunking, embeddings e recuperação. |
| **Documento** (`Document`) | Um arquivo ou registro de origem, como um PDF, uma página web ou uma linha de banco. |
| **Versão de documento** (`DocumentVersion`) | O conteúdo de um documento em um momento. Uma atualização cria uma versão nova. |
| **Chunk** | Um trecho de uma versão de documento. O chunk é a unidade de indexação e de recuperação. |
| **Espaço de embeddings** (`EmbeddingSpace`) | A combinação de modelo de embeddings, dimensão e versão. Vetores de espaços diferentes não se comparam. |
| **Retriever** | Um componente que recebe uma consulta e devolve chunks com pontuação. |
| **Fusão** | A combinação das listas de vários retrievers em uma lista única. O padrão é RRF. |
| **Reranker** | Um componente que reordena os chunks candidatos com um modelo mais preciso. |
| **Contexto** | Os chunks que o sistema envia ao LLM junto com a pergunta. |
| **Citação** | A referência de uma afirmação da resposta ao chunk que sustenta a afirmação. |
| **Port** | Uma interface abstrata do núcleo. Exemplo: `EmbeddingProvider`. |
| **Adapter** | Uma implementação concreta de um port. Exemplo: `OllamaEmbeddingProvider`. |
| **Job de ingestão** (`IngestionJob`) | Uma execução do pipeline de ingestão, com estado e histórico. |
| **Cliente MCP** | Qualquer agente, IDE ou aplicação que implementa o lado cliente do Model Context Protocol. Exemplos: Claude Code, Hermes Agent, agentes LangGraph. |
| **Agent Skill** | Uma pasta com um arquivo `SKILL.md` que ensina um agente a fazer uma tarefa. O formato segue o padrão aberto Agent Skills (agentskills.io). |

---

## 3. Princípios de arquitetura

1. **Clean Architecture.** O domínio não importa infraestrutura. A dependência aponta sempre para dentro: adapters → aplicação → domínio.
2. **SOLID.** Cada componente tem uma responsabilidade.
3. **Injeção de dependência.** A aplicação recebe os adapters prontos. A aplicação não cria adapters.
4. **Adapter Pattern.** Cada serviço externo fica atrás de um port: banco, embeddings, LLM, reranker, armazenamento de objetos, cache.
5. **Factory e registro de plugins.** Uma factory cria cada adapter a partir do nome na configuração. Um pacote externo registra um adapter novo por entry point Python (grupo `vlade_rag.plugins`). O núcleo não muda.
6. **12-Factor App.** A configuração vem de variáveis de ambiente e de arquivos externos. O processo escreve logs em `stdout`. O processo não guarda estado local.
7. **Testes primeiro.** Cada port tem uma suíte de testes de contrato. Cada adapter deve passar na suíte do port que ele implementa.
8. **Núcleo sem orquestrador.** O núcleo funciona sem LangGraph, sem Kestra e sem MCP. Esses componentes são camadas externas que chamam o núcleo.
9. **Observável por padrão.** Cada etapa do pipeline cria um span OpenTelemetry. Um adapter novo herda essa instrumentação.
10. **Isolamento de tenant em toda camada.** Nenhuma consulta ao banco roda sem um `tenant_id`.

---

## 4. Responsabilidades do framework

O Vlade-RAG separa cinco responsabilidades de domínio e três responsabilidades transversais.

### 4.1. Responsabilidades de domínio

| Responsabilidade | O que faz | Módulo Python |
|---|---|---|
| **Ingestion** | Recebe documentos, extrai o texto, limpa o texto, divide o texto em chunks, gera embeddings. | `vlade_rag.ingestion`, `vlade_rag.embeddings` |
| **Knowledge** | Armazena e indexa tenants, bases, documentos, versões, chunks e vetores. | `vlade_rag.knowledge` |
| **Retrieval** | Analisa a consulta, roda os retrievers, faz a fusão e o reranking. | `vlade_rag.retrieval`, `vlade_rag.reranking` |
| **Generation** | Monta o contexto, chama o LLM, gera a resposta com citações. | `vlade_rag.generation` |
| **Evaluation** | Mede a qualidade da recuperação e das respostas. | `vlade_rag.evaluation` |

### 4.2. Responsabilidades transversais

| Responsabilidade | O que faz | Módulo Python |
|---|---|---|
| **Interfaces** | Expõem o núcleo por API REST, MCP e CLI. | `vlade_rag.api`, `vlade_rag.mcp`, `vlade_rag.cli` |
| **Orquestração** | Conduz o fluxo de consulta (LangGraph) e os processos operacionais (Kestra). | `vlade_rag.orchestration`, `vlade_rag.integrations.kestra` |
| **Operação** (`vlade-rag-ops`) | Health checks, métricas, auditoria, reindexação, manutenção e observabilidade. | `vlade_rag.ops`, `vlade_rag.observability` |

---

## 5. Camadas

```text
┌──────────────────────────────────────────────────────────────┐
│ INTERFACES        FastAPI (REST)   MCP Server   CLI          │
├──────────────────────────────────────────────────────────────┤
│ ORQUESTRAÇÃO      LangGraph (consulta)   Kestra (operação)   │
├──────────────────────────────────────────────────────────────┤
│ APLICAÇÃO         Casos de uso: IngestDocument, Query,       │
│                   Search, Reindex, Evaluate, DeleteDocument  │
├──────────────────────────────────────────────────────────────┤
│ DOMÍNIO           Entidades, objetos de valor, ports         │
├──────────────────────────────────────────────────────────────┤
│ ADAPTERS          Postgres, Qdrant, Ollama, OpenAI, Gemini,  │
│                   OpenRouter, BGE, MinIO, Redis, Langfuse    │
├──────────────────────────────────────────────────────────────┤
│ MOTOR RUST        vlade_rag_core (PyO3): funções de CPU      │
└──────────────────────────────────────────────────────────────┘
```

Regras de dependência:

- O domínio não importa nenhuma outra camada.
- A aplicação importa só o domínio.
- Os adapters implementam ports do domínio.
- As interfaces e a orquestração chamam apenas casos de uso da aplicação. Uma interface não deve chamar um adapter diretamente.
- O motor Rust não acessa rede, banco ou disco. O motor Rust recebe dados do Python e devolve dados ao Python.

---

## 6. Divisão entre Rust e Python

O rascunho original não definia o papel do Rust. Esta seção define o papel do Rust.

**Regra:** o Rust faz trabalho de CPU puro e determinístico. O Python faz I/O, orquestração e integração com bibliotecas de IA.

| Tarefa | Linguagem | Motivo |
|---|---|---|
| Normalização de texto (Unicode, espaços, hifenização) | Rust | CPU, volume alto na ingestão |
| Chunking (por tokens, por frase, recursivo, por estrutura Markdown) | Rust | CPU, volume alto na ingestão |
| Contagem de tokens | Rust (crate `tokenizers`) | CPU |
| Hash de conteúdo e deduplicação (exata e aproximada) | Rust | CPU |
| Fusão RRF e normalização de pontuação | Rust | CPU, chamada em toda consulta |
| Extração de texto de PDF, DOCX e HTML | Python | Ecossistema maduro em Python |
| Chamadas a LLM, embeddings e reranker | Python | I/O e SDKs de provedores |
| Acesso a banco, cache e armazenamento | Python | I/O |
| API, MCP, CLI, LangGraph | Python | Ecossistema |

Requisitos do motor Rust:

- O motor Rust deve expor as funções por PyO3. O Maturin empacota o motor Rust como módulo Python.
- Cada função Rust deve ter uma implementação de referência em Python puro no pacote. Um teste deve comparar as duas implementações. Assim o framework funciona mesmo quando o binário Rust não está disponível para a plataforma.
- O motor Rust deve liberar o GIL nas funções de lote.

---

## 7. Modelo de domínio

Entidades mínimas:

```text
Tenant ─┬─< KnowledgeBase ─┬─< Document ─< DocumentVersion ─< Chunk ─< ChunkEmbedding
        │                  └── EmbeddingSpace (ativo)              │
        ├─< ApiKey / Principal                                     └── EmbeddingSpace
        ├─< IngestionJob ─< IngestionStep
        ├─< QueryLog
        └─< AuditEvent
```

Requisitos do modelo:

1. Toda tabela com dados de cliente deve ter a coluna `tenant_id`.
2. Uma `KnowledgeBase` aponta para um `EmbeddingSpace` ativo. Uma troca de modelo de embeddings cria um espaço novo. O sistema não mistura vetores de espaços diferentes na mesma busca.
3. Uma `DocumentVersion` guarda o hash do conteúdo. Se o hash de uma versão nova é igual ao hash da versão atual, o sistema não reprocessa o documento.
4. Um `Chunk` guarda: texto, posição no documento (página, offset inicial, offset final), seção, metadados livres em JSONB e a contagem de tokens.
5. Uma exclusão de documento apaga as versões, os chunks, os vetores e o arquivo original no armazenamento de objetos. Essa regra atende ao direito de eliminação da LGPD.
6. Um `IngestionJob` tem os estados `pending`, `running`, `succeeded`, `failed` e `cancelled`.

---

## 8. Ports (contratos do núcleo)

Cada port é uma classe abstrata Python (`typing.Protocol` ou `abc.ABC`) em `vlade_rag.core.ports`. Os nomes abaixo são obrigatórios. As assinaturas são uma proposta inicial. Você pode refinar as assinaturas no `ARCHITECTURE.md`.

| Port | Responsabilidade | Adapters da primeira versão |
|---|---|---|
| `DocumentSource` | Lê documentos de uma origem | Upload direto, sistema de arquivos, S3 |
| `DocumentParser` | Extrai texto e estrutura de um arquivo | Texto, Markdown, HTML, PDF, DOCX |
| `TextNormalizer` | Limpa e normaliza o texto | Rust |
| `Chunker` | Divide o texto em chunks | Rust: tokens, recursivo, Markdown |
| `EmbeddingProvider` | Gera vetores | Ollama, Sentence Transformers, OpenAI-compatível |
| `KnowledgeRepository` | Grava e lê entidades do domínio | PostgreSQL |
| `VectorIndex` | Grava e busca vetores | pgvector. Qdrant na fase 5 |
| `LexicalIndex` | Busca por palavras | PostgreSQL `tsvector`, `pg_search` (BM25), `pg_trgm` |
| `Retriever` | Busca chunks para uma consulta | Denso, léxico, fuzzy, híbrido |
| `FusionStrategy` | Combina listas de resultados | RRF, combinação ponderada |
| `Reranker` | Reordena candidatos | BGE Reranker, cross-encoder genérico, nenhum |
| `QueryTransformer` | Reescreve ou expande a consulta | Nenhum, reescrita por LLM, multi-query, HyDE |
| `LLMProvider` | Gera texto | Ollama, OpenAI, Gemini, OpenRouter |
| `PromptRegistry` | Fornece templates de prompt versionados | Arquivos locais, Langfuse |
| `ObjectStorage` | Guarda os arquivos originais | API S3 (MinIO ou compatível), sistema de arquivos |
| `Cache` | Guarda resultados reutilizáveis | Redis, memória, nenhum |
| `Evaluator` | Mede a qualidade | Métricas de recuperação, RAGAS |
| `Tracer` | Registra spans e eventos de IA | OpenTelemetry, Langfuse |

Proposta de assinatura para três ports centrais:

```python
class EmbeddingProvider(Protocol):
    space: EmbeddingSpace  # modelo, dimensão, versão
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...

class Retriever(Protocol):
    name: str
    async def retrieve(self, query: Query, ctx: TenantContext, top_k: int) -> list[ScoredChunk]: ...

class LLMProvider(Protocol):
    async def generate(self, messages: list[Message], params: GenerationParams) -> Generation: ...
    def stream(self, messages: list[Message], params: GenerationParams) -> AsyncIterator[GenerationChunk]: ...
```

Requisitos dos ports:

- Toda operação de I/O deve ser assíncrona (`async`).
- Todo método que lê ou grava dados de cliente deve receber um `TenantContext`.
- Cada port deve ter uma suíte de testes de contrato em `tests/contract/`.

---

## 9. Pipeline de ingestão

```text
RECEBER → VALIDAR → GUARDAR ORIGINAL → EXTRAIR → NORMALIZAR → DEDUPLICAR
       → CHUNKING → EMBEDDINGS (em lote) → INDEXAR VETORES → INDEXAR TEXTO
       → VALIDAR ÍNDICES → PUBLICAR VERSÃO
```

Requisitos:

1. A etapa VALIDAR verifica tipo de arquivo, tamanho máximo, cota do tenant e presença de malware, se um scanner estiver configurado.
2. Cada etapa é idempotente. Uma nova execução de uma etapa com a mesma entrada não duplica dados.
3. A etapa PUBLICAR torna a versão nova visível para as consultas de forma atômica. Uma consulta nunca vê uma versão indexada pela metade.
4. O caso de uso `IngestDocument` roda o pipeline inteiro dentro de um processo. O Kestra chama esse caso de uso por lote. O pipeline não depende do Kestra.
5. Se uma etapa falha, o sistema grava o erro no `IngestionStep` e marca o job como `failed`. O sistema não publica a versão.
6. A geração de embeddings usa lotes com tamanho configurável e respeita o limite de requisições do provedor.

---

## 10. Pipeline de consulta

```text
consulta
  → análise da consulta (idioma, intenção, filtros)
  → transformação da consulta (opcional)
  → recuperação híbrida em paralelo
       ├── densa (pgvector)
       ├── léxica BM25 (pg_search) ou tsvector
       └── fuzzy (pg_trgm), opcional
  → fusão RRF
  → reranking (opcional)
  → montagem do contexto (limite de tokens, deduplicação, ordem)
  → geração com citações
  → validação da resposta (citações existem, resposta fundamentada)
  → resposta
```

Requisitos:

1. A fusão RRF usa a fórmula `score(d) = Σ 1 / (k + rank_i(d))`. O valor padrão de `k` é 60. A configuração da base de conhecimento pode mudar `k`.
2. A busca léxica em português usa uma configuração de busca textual com `unaccent` e o dicionário `portuguese`.
3. A resposta deve conter a lista de citações. Cada citação contém `document_id`, `chunk_id`, título do documento e posição no documento.
4. Se o contexto não sustenta uma resposta, o sistema responde que não encontrou a informação nas fontes. O sistema não deve inventar uma resposta.
5. O sistema trata o texto dos chunks como dado, não como instrução. O prompt de geração deve separar as instruções do sistema e o conteúdo recuperado. Essa regra reduz o risco de injeção de prompt por documento.
6. A API oferece dois modos: `search` devolve só os chunks, `query` devolve a resposta gerada.
7. A API oferece resposta em streaming para o modo `query`.

---

## 11. Multi-tenancy e segurança

### 11.1. Isolamento

1. O banco deve usar Row-Level Security (RLS) do PostgreSQL em toda tabela com `tenant_id`. A aplicação define o tenant da sessão com `SET LOCAL app.tenant_id` em cada transação.
2. A aplicação também filtra por `tenant_id` em cada consulta. O RLS é a segunda barreira, não a única.
3. Um teste automatizado deve tentar ler dados de outro tenant por cada interface: API, MCP e CLI. O teste passa só se a leitura falha.
4. As chaves de cache e os caminhos no armazenamento de objetos começam com o `tenant_id`.

### 11.2. Autenticação e autorização

1. A primeira versão usa chaves de API por tenant, guardadas como hash.
2. A arquitetura deve aceitar OIDC/OAuth 2.1 depois, sem mudar os casos de uso.
3. Cada principal tem papéis. Papéis mínimos: `reader`, `writer`, `admin`.
4. Operações de escrita, exclusão e reindexação exigem o papel `writer` ou `admin`.

### 11.3. Proteções

- Limite de requisições por tenant e por chave.
- Auditoria de toda operação de escrita e de toda chamada MCP em `AuditEvent`.
- Segredos só em variáveis de ambiente ou em um gerenciador de segredos. Nenhum segredo no código, nos logs ou nos traces.
- O sistema nunca envia credenciais ao LLM.
- Mascaramento opcional de dados pessoais (PII) nos logs e nos traces.

---

## 12. MCP (Model Context Protocol)

O MCP é uma interface de primeira classe do Vlade-RAG, com o mesmo nível da API REST. O módulo `vlade_rag.mcp` (nome do serviço: `vlade-rag-mcp`) expõe o núcleo para agentes, IDEs e outros clientes MCP.

```text
QUALQUER CLIENTE MCP
(exemplos: Claude Code, Hermes Agent, agentes LangGraph, IDEs)
                │
                ▼
        vlade-rag-mcp  ── auth ── policies ── auditoria
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
   Tools    Resources   Prompts
     └──────────┼──────────┘
                ▼
        Casos de uso (camada de aplicação)
```

Requisitos:

1. O servidor MCP usa o SDK oficial `mcp` para Python.
2. O servidor oferece dois transportes: `stdio` para uso local e Streamable HTTP para uso remoto.
3. No transporte HTTP, o servidor exige autenticação. No transporte `stdio`, o servidor lê a credencial de uma variável de ambiente.
4. Os nomes das ferramentas usam `snake_case` com o prefixo `vlade_`. Alguns clientes MCP rejeitam pontos em nomes de ferramentas.
5. O servidor MCP chama apenas casos de uso. O servidor MCP não acessa o banco diretamente.
6. O servidor MCP segue só a especificação do protocolo. O servidor não deve ter código específico para um cliente. Claude Code e Hermes Agent são exemplos de clientes, não requisitos.
7. A CI testa o servidor com o MCP Inspector. Antes de cada release, um teste manual verifica o servidor com pelo menos dois clientes diferentes, por exemplo Claude Code e Hermes Agent.

### 12.1. Agent Skill do Vlade-RAG

O projeto publica uma Agent Skill em `skills/vlade-rag/SKILL.md`. A skill ensina um agente a usar as ferramentas `vlade_*`: quando usar `vlade_search` e quando usar `vlade_query`, como ler as citações, como responder quando a base não tem a informação.

Requisitos:

1. A skill segue o padrão aberto Agent Skills (agentskills.io). Assim a mesma skill funciona no Claude Code, no Hermes Agent e em outros agentes compatíveis.
2. A skill não contém credenciais nem endereços de servidor fixos.
3. A skill usa a licença MIT do projeto.
4. O texto da skill está em português do Brasil e passa no linter da skill `asd-ste100-pt-br`, no modo Estrito.

Ferramentas:

| Ferramenta | Tipo | Papel mínimo |
|---|---|---|
| `vlade_search` | Leitura | `reader` |
| `vlade_query` | Leitura | `reader` |
| `vlade_list_knowledge_bases` | Leitura | `reader` |
| `vlade_get_document` | Leitura | `reader` |
| `vlade_get_ingestion_status` | Leitura | `reader` |
| `vlade_ingest_document` | Escrita | `writer` |
| `vlade_delete_document` | Escrita destrutiva | `admin` |
| `vlade_reindex_knowledge_base` | Escrita destrutiva | `admin` |
| `vlade_evaluate` | Operação | `admin` |

Resources:

- `vlade://kb/{kb_id}` — metadados da base de conhecimento.
- `vlade://kb/{kb_id}/documents/{document_id}` — documento e metadados.

Prompts:

- `vlade_answer_with_citations` — responde com base nas fontes e cita cada fonte.
- `vlade_summarize_document` — resume um documento.

Regras de segurança do MCP:

1. O servidor ativa só as ferramentas de leitura por padrão. A configuração ativa as ferramentas de escrita, por tenant.
2. Uma ferramenta destrutiva exige o parâmetro `confirm: true`. Sem esse parâmetro, a ferramenta devolve uma prévia do efeito e não executa.
3. O servidor valida o papel do principal em cada chamada.
4. O servidor grava cada chamada em `AuditEvent`.
5. O servidor aplica o mesmo limite de requisições da API.

Integrações MCP de terceiros, para uso dos agentes que operam o sistema:

| Componente | Integração MCP |
|---|---|
| Kestra | Servidor MCP que expõe workflows como ferramentas |
| Langfuse | Servidor MCP que expõe traces e avaliações |
| Grafana | Servidor MCP que consulta Prometheus, Loki e Tempo |
| LangGraph | `langchain-mcp-adapters` para consumir ferramentas MCP |

---

## 13. Orquestração: LangGraph e Kestra

Os dois componentes têm papéis diferentes. Não troque um pelo outro.

| Característica | Kestra | LangGraph |
|---|---|---|
| Papel | Orquestração operacional | Orquestração do raciocínio |
| Definição | YAML | Python |
| Gatilho | Agenda, evento, API | Cada consulta |
| Duração típica | Minutos ou horas | Segundos |
| Uso no Vlade-RAG | Ingestão em lote, reindexação, sincronização, avaliação agendada, backup | Fluxo de consulta, reescrita, recuperação, validação da resposta |

Regras:

1. O Kestra decide quando e com que frequência um processo operacional roda.
2. O LangGraph decide como o sistema conduz uma consulta.
3. O núcleo do Vlade-RAG fornece os casos de uso que os dois chamam.
4. O Kestra não deve ficar no caminho de uma consulta síncrona. Essa camada só aumenta a latência.
5. O fluxo de consulta tem duas implementações: um pipeline linear em Python puro, que é o padrão, e um grafo LangGraph, que a configuração ativa. Os dois usam os mesmos casos de uso.
6. O Kestra chama o Vlade-RAG pela API REST ou pela CLI `vlade-rag` em um container. Os flows Kestra ficam em `deploy/kestra/flows/`.
7. A primeira versão não usa Celery. Se o projeto precisar de uma fila de alta frequência depois, um ADR avalia essa inclusão.

Flows Kestra da primeira versão:

| Flow | Gatilho |
|---|---|
| `ingest_batch` | API ou novo arquivo no armazenamento de objetos |
| `sync_source` | Agenda |
| `reindex_knowledge_base` | Manual ou troca de espaço de embeddings |
| `evaluate_nightly` | Agenda diária |
| `backup` | Agenda diária |

---

## 14. Observabilidade

Três domínios:

| Domínio | Ferramenta | O que monitora |
|---|---|---|
| IA | Langfuse | Prompts, modelo, tokens, custo, documentos recuperados, avaliações |
| Aplicação | OpenTelemetry | Traces, métricas e logs, com correlação entre serviços |
| Infraestrutura | Prometheus, Loki, Tempo, Grafana (stack LGTM) com Grafana Alloy | CPU, memória, latência, disponibilidade, logs |

Fluxo de telemetria:

```text
Python (OTel SDK) ─┐
Rust (via spans do Python) ─┼─→ Grafana Alloy ─┬─→ Prometheus (métricas)
Kestra (OTel + /metrics) ─┘                 ├─→ Loki (logs)
                                            └─→ Tempo (traces)
                                                      ↓
                                                   Grafana
Python (Langfuse SDK, baseado em OTel) ──────────→ Langfuse
```

Requisitos:

1. O coletor é o Grafana Alloy. Não use o Grafana Agent, que chegou ao fim de vida.
2. Cada consulta cria um trace com estes spans: `query_analysis`, `query_transform`, `retrieval.dense`, `retrieval.lexical`, `retrieval.fuzzy`, `fusion`, `rerank`, `context_assembly`, `llm_generation`, `response_validation`.
3. Cada span grava `tenant_id`, `knowledge_base_id` e o nome do adapter.
4. Cada log é JSON estruturado e contém `trace_id`.
5. Se o Langfuse não está configurado, o sistema continua a funcionar. Só o envio ao Langfuse para.

Dashboards:

| Dashboard | Indicadores |
|---|---|
| RAG Performance | Latência por etapa, Recall@K, Precision@K, MRR, NDCG |
| LLM Observability | Tokens, custo, modelo, taxa de erro |
| Retrieval Analytics | Contribuição de cada retriever, efeito do RRF e do reranking |
| Infrastructure | CPU, RAM, PostgreSQL, Redis, armazenamento de objetos |
| Workflow Monitoring | Execuções Kestra, ingestões, falhas, reprocessamentos |

Alertas:

- Falhas consecutivas de ingestão.
- Aumento da latência de recuperação.
- Erros de geração.
- Falha de conexão com um provedor.
- Crescimento de fila.
- PostgreSQL indisponível.
- Consumo excessivo de memória.
- Queda da qualidade nas avaliações.

---

## 15. Avaliação

1. O projeto mantém datasets de referência em `evals/datasets/`. Cada item tem pergunta, resposta esperada e IDs dos chunks relevantes.
2. Métricas de recuperação, calculadas sem LLM: Recall@K, Precision@K, MRR, NDCG.
3. Métricas de resposta, calculadas com RAGAS: faithfulness, answer relevancy, context precision, context recall.
4. A CI roda a avaliação de recuperação em cada pull request. Se uma métrica cai mais que o limite configurado, a CI falha.
5. O Kestra roda a avaliação completa com RAGAS por agenda. O Langfuse guarda os resultados como experimentos.
6. O resultado de cada avaliação registra a configuração usada: modelos, chunking, retrievers, `k` do RRF, reranker e versão dos prompts.

---

## 16. Stack tecnológica

| Camada | Tecnologia | Fase |
|---|---|---|
| Linguagem | Python 3.12 ou mais recente, Rust estável | 0 |
| Pacotes Python | `uv` (workspace) | 0 |
| Binding Rust | PyO3 e Maturin | 1 |
| API | FastAPI | 1 |
| Banco | PostgreSQL 17 | 1 |
| Acesso ao banco | SQLAlchemy 2 (assíncrono), asyncpg, pgvector-python, Alembic (ADR-0004) | 1 |
| Busca vetorial | pgvector (índice HNSW) | 1 |
| Busca textual | `tsvector`, `unaccent` | 1 |
| Busca fuzzy | `pg_trgm` | 1 |
| BM25 | `pg_search` (ParadeDB). Veja a decisão D1 | 3 |
| Fusão | RRF | 1 |
| Embeddings | Ollama, Sentence Transformers, API compatível com OpenAI | 1 |
| LLM | Ollama, OpenAI, Gemini, OpenRouter | 1 |
| Extração de documentos | Docling para PDF e DOCX. Veja a decisão D6 | 1 |
| CLI | Typer | 1 |
| MCP | SDK oficial `mcp` para Python | 2 |
| Reranking | BGE Reranker, cross-encoder | 3 |
| Orquestração de IA | LangGraph | 3 |
| Avaliação | RAGAS e métricas próprias | 3 |
| Observabilidade de IA | Langfuse | 3 |
| Telemetria | OpenTelemetry | 1 |
| Workflows | Kestra | 4 |
| Coletor | Grafana Alloy | 4 |
| Métricas, logs, traces, dashboards | Prometheus, Loki, Tempo, Grafana | 4 |
| Cache | Valkey, protocolo compatível com Redis. Veja a decisão D3 | 2 |
| Armazenamento de objetos | API S3: MinIO ou compatível. Veja a decisão D2 | 2 |
| Banco vetorial alternativo | Qdrant | 5 |
| Containers | Docker e Docker Compose | 0 |

### 16.1. Política de licenças das dependências

O Vlade-RAG usa a licença MIT. Um usuário deve conseguir usar o núcleo em um produto comercial fechado sem obrigação extra. Por isso:

1. O núcleo e a instalação padrão (`pip install vlade-rag`) usam só dependências com licença permissiva: MIT, BSD, Apache-2.0, ISC, PSF, Unlicense, Zlib.
2. Uma dependência com licença MPL-2.0 é aceita. Registre essa dependência no ADR de licenças.
3. Uma dependência com licença GPL, LGPL, AGPL, SSPL, BUSL, RSAL ou outra licença não permissiva fica só em um extra opcional. O nome do extra e o README do extra devem informar a licença.
4. Um serviço externo que roda em processo separado, como uma extensão PostgreSQL ou um servidor de armazenamento, não entra no pacote Python. A documentação de implantação deve informar a licença desse serviço.
5. A CI verifica as licenças das dependências do núcleo e falha se encontra uma licença fora da lista do item 1 ou do item 2.
6. O código copiado de outro projeto mantém o aviso de copyright original. A licença do código copiado deve ser compatível com MIT.

### 16.2. Idioma

Regras de configuração por idioma:

- O código, os identificadores, os nomes de tabelas e as mensagens de log usam inglês.
- A documentação usa português do Brasil.
- Os prompts padrão de geração existem em português do Brasil e em inglês.

---

## 17. Perfis de ambiente

O ambiente de desenvolvimento é um notebook com 8 GB de RAM. Não rode a stack completa nesse notebook. O Docker Compose usa `profiles` para separar os perfis.

| Perfil | Serviços | Uso |
|---|---|---|
| `dev` | API, PostgreSQL com pgvector, Redis. Ollama externo ou provedor remoto. Langfuse Cloud ou desativado | Desenvolvimento no notebook |
| `staging` | `dev` mais Kestra, MinIO, Langfuse, coletor OpenTelemetry | Testes de integração no HomeLab |
| `prod` | Todos os serviços, inclusive Prometheus, Loki, Tempo, Grafana, Alloy e workers Kestra dimensionados | Produção |

Observação: o Kestra roda na JVM. O Langfuse auto-hospedado precisa de ClickHouse, Redis, PostgreSQL e armazenamento S3. Os dois juntos consomem a maior parte de 8 GB de RAM. Por isso os dois ficam fora do perfil `dev`.

---

## 18. Estrutura do repositório

```text
vlade-rag/
├── VLADE-RAG.md                 # este documento
├── CLAUDE.md                    # regras para agentes neste repositório
├── LICENSE                      # MIT
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md                  # como relatar vulnerabilidades
├── CHANGELOG.md
├── .github/                     # CI, templates de issue e de pull request
├── pyproject.toml               # workspace uv
├── Cargo.toml                   # workspace Rust
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── MCP_SPEC.md
│   ├── ROADMAP.md
│   ├── adr/
│   └── referencia/
├── packages/
│   ├── python/
│   │   └── vlade_rag/
│   │       ├── core/
│   │       │   ├── domain/          # entidades e objetos de valor
│   │       │   ├── ports/           # interfaces abstratas
│   │       │   ├── application/     # casos de uso
│   │       │   ├── config/          # configuração tipada (pydantic-settings)
│   │       │   └── registry/        # factories e plugins
│   │       ├── ingestion/
│   │       │   ├── sources/
│   │       │   └── parsers/
│   │       ├── embeddings/
│   │       ├── knowledge/
│   │       │   ├── postgres/        # repositório, migrações, RLS
│   │       │   └── qdrant/
│   │       ├── retrieval/
│   │       ├── reranking/
│   │       ├── generation/
│   │       │   ├── providers/       # ollama, openai, gemini, openrouter
│   │       │   └── prompts/
│   │       ├── orchestration/
│   │       │   ├── pipeline/        # fluxo linear padrão
│   │       │   └── langgraph/
│   │       ├── evaluation/
│   │       │   ├── metrics/
│   │       │   └── ragas/
│   │       ├── api/                 # FastAPI
│   │       ├── mcp/
│   │       │   ├── server/
│   │       │   ├── tools/
│   │       │   ├── resources/
│   │       │   ├── prompts/
│   │       │   ├── auth/
│   │       │   └── policies/
│   │       ├── cli/
│   │       ├── observability/
│   │       │   ├── opentelemetry/
│   │       │   └── langfuse/
│   │       ├── ops/                 # health, auditoria, manutenção (vlade-rag-ops)
│   │       └── integrations/
│   │           ├── kestra/
│   │           ├── grafana/
│   │           └── external/
│   └── rust/
│       └── vlade_rag_core/
│           ├── src/
│           │   ├── normalize.rs
│           │   ├── chunking/
│           │   ├── tokens.rs
│           │   ├── dedup.rs
│           │   └── fusion.rs
│           └── Cargo.toml
├── deploy/
│   ├── compose/                 # docker-compose.yml com profiles dev, staging, prod
│   ├── postgres/                # imagem com pgvector, pg_trgm, unaccent, pg_search
│   ├── kestra/flows/
│   ├── alloy/
│   └── grafana/dashboards/
├── skills/
│   └── vlade-rag/               # Agent Skill para clientes MCP (seção 12.1)
│       └── SKILL.md
├── evals/
│   └── datasets/
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    └── e2e/
```

Distribuição do pacote Python (ADR-0003):

- O projeto publica duas distribuições: `vlade-rag` (Python puro) e `vlade-rag-core` (motor Rust).
- O pacote `vlade-rag` instala só o núcleo. O extra `native` instala o motor Rust.
- Cada grupo de adapters é um extra opcional. Exemplo: `pip install "vlade-rag[native,postgres,ollama,openai,mcp,langgraph]"`.
- Uma aplicação que usa o Vlade-RAG como biblioteca não precisa instalar FastAPI, Kestra ou LangGraph.

---

## 19. Requisitos não funcionais

Os números abaixo são metas iniciais propostas. Confirme ou ajuste os números no `PROJECT_SPEC.md`.

| Requisito | Meta inicial |
|---|---|
| Latência p95 de `search`, sem reranking, base com 1 milhão de chunks | ≤ 300 ms |
| Latência p95 de `search`, com reranking de 50 candidatos | ≤ 1 s |
| Primeiro token em `query` com streaming, excluindo o tempo do LLM remoto | ≤ 1,5 s |
| Vazão de ingestão, sem contar o tempo de embeddings | ≥ 50 páginas por segundo por worker |
| Cobertura de testes do núcleo (`core`, `retrieval`, `ingestion`) | ≥ 85% |
| Disponibilidade da API em produção | ≥ 99,5% |
| Vazamento de dados entre tenants | Zero. Um teste automatizado bloqueia a CI |

---

## 20. Roadmap

### Fase 0 — Fundação

- Documentos fundadores e ADRs iniciais.
- Arquivos de projeto open source: `LICENSE` (MIT), `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, templates de issue e de pull request.
- Campo de licença `MIT` no `pyproject.toml` e no `Cargo.toml`.
- Workspace `uv` e workspace Rust com Maturin.
- CI: lint (`ruff`, `mypy`, `clippy`, `rustfmt`), testes, build do pacote, verificação de licenças (seção 16.1).
- Docker Compose com o perfil `dev`.

**Aceite:** a CI passa, inclusive a verificação de licenças. O comando `docker compose --profile dev up` sobe a API com o endpoint `/health`.

### Fase 1 — Núcleo mínimo

- Domínio, ports e casos de uso `IngestDocument`, `Search`, `Query`, `DeleteDocument`.
- PostgreSQL com pgvector, `tsvector`, `unaccent`, `pg_trgm` e RLS.
- Parsers de texto, Markdown, HTML, PDF e DOCX.
- Motor Rust: normalização, chunking, contagem de tokens, hash, RRF.
- Embeddings e LLM: Ollama e API compatível com OpenAI.
- Recuperação híbrida (densa e `tsvector`) com fusão RRF.
- Geração com citações.
- API REST e CLI.
- OpenTelemetry básico.

**Aceite:** um usuário ingere 100 documentos em português e recebe respostas com citações corretas. O teste de isolamento entre tenants passa. Os testes de contrato de cada adapter passam.

### Fase 2 — Interfaces e armazenamento

- Servidor MCP com as ferramentas de leitura.
- Agent Skill `skills/vlade-rag/` (seção 12.1).
- Armazenamento de objetos pela API S3.
- Cache Redis para embeddings de consulta.
- Chaves de API, papéis, limite de requisições e auditoria.
- Provedores Gemini e OpenRouter.

**Aceite:** dois clientes MCP diferentes, por exemplo Claude Code e Hermes Agent, consultam uma base pelo MCP com a Agent Skill instalada. Uma chave de outro tenant recebe acesso negado.

### Fase 3 — Qualidade

- Reranking com BGE.
- Transformação de consulta.
- Fluxo de consulta em LangGraph.
- BM25 com `pg_search`, se a decisão D1 confirmar.
- Datasets de referência, métricas de recuperação e RAGAS.
- Langfuse.
- Gate de qualidade na CI.

**Aceite:** um relatório compara a configuração da fase 1 com a configuração da fase 3 no mesmo dataset. O relatório mostra Recall@10 e faithfulness das duas configurações.

### Fase 4 — Operação

- Flows Kestra da seção 13.
- Reindexação sem parada (espaço de embeddings novo e troca atômica).
- Stack LGTM, Grafana Alloy, dashboards e alertas da seção 14.
- Ferramentas MCP de escrita, com confirmação.
- Módulo `vlade-rag-ops` completo.

**Aceite:** uma reindexação completa de uma base roda pelo Kestra enquanto as consultas continuam a responder. Os cinco dashboards mostram dados reais.

### Fase 5 — Extensões

- Adapter Qdrant.
- Conectores de origem, como Google Drive, sites e bancos SQL.
- Cache semântico.
- OIDC/OAuth 2.1.
- Publicação do pacote no PyPI.

---

## 21. Decisões

Todas as decisões abaixo têm o status `Aceito` desde 2026-11-19. O índice completo dos ADRs está em [`docs/adr/README.md`](docs/adr/README.md).

| ID | Decisão | ADR |
|---|---|---|
| D1 | `tsvector` é o padrão do `LexicalIndex`. O `pg_search` (BM25, AGPL-3.0) é só um adapter opcional, com imagem PostgreSQL própria | ADR-0005 |
| D2 | O port `ObjectStorage` usa a API S3. O perfil `dev` usa o sistema de arquivos. MinIO nos perfis `staging` e `prod`. Antes da fase 2, verifique a distribuição atual do MinIO. Se a imagem não estiver disponível, use SeaweedFS, Garage ou RustFS | ADR-0006 |
| D3 | Valkey (BSD-3-Clause) é o cache padrão. O cliente `redis-py` funciona com Valkey e com Redis | ADR-0007 |
| D4 | `bge-m3` é o modelo de embeddings padrão (multilíngue, 1024 dimensões) | ADR-0008 |
| D5 | `bge-reranker-v2-m3` é o reranker padrão (multilíngue) | ADR-0008 |
| D6 | Docling (MIT) extrai PDF e DOCX. O PyMuPDF (AGPL-3.0) só pode entrar como extra opcional | ADR-0010 |
| D7 | O Vlade-RAG é open source, com licença MIT. A política de licenças da seção 16.1 vale para todas as dependências | ADR-0001 |
| D8 | O Vlade-RAG atende qualquer cliente MCP. O Hermes Agent (Nous Research) e o Claude Code são exemplos. O projeto publica uma Agent Skill no padrão aberto (seção 12.1) | ADR-0013 |
| D9 | O fluxo de consulta da versão 1 não tem human-in-the-loop | ADR-0014 |

---

## 22. Documentos fundadores

Crie estes documentos na fase 0, nesta ordem:

| Ordem | Arquivo | Conteúdo |
|---|---|---|
| 1 | `docs/PROJECT_SPEC.md` | Objetivo, escopo, fora do escopo, casos de uso, requisitos funcionais e não funcionais com metas confirmadas |
| 2 | `docs/ARCHITECTURE.md` | Camadas, ports com assinaturas finais, modelo de dados com o esquema SQL, pipelines, divisão Rust e Python, multi-tenancy, observabilidade |
| 3 | `docs/MCP_SPEC.md` | Ferramentas com esquema JSON de entrada e saída, resources, prompts, autenticação, papéis, auditoria, erros |
| 4 | `docs/ROADMAP.md` | Fases, entregas, critérios de aceite, riscos |
| 5 | `docs/adr/0001-licenca-mit.md` em diante | Uma decisão por arquivo. O ADR-0001 registra a licença MIT e a política da seção 16.1 |
| 6 | `CLAUDE.md` | Regras curtas para agentes que trabalham neste repositório |

Formato de cada ADR:

```markdown
# ADR-NNNN: <título>
- Status: Proposto | Aceito | Substituído por ADR-NNNN
- Data: AAAA-MM-DD
## Contexto
## Decisão
## Alternativas avaliadas
## Consequências
```

---

## 23. Regras para o agente que implementa

1. Escreva o código em inglês. Escreva a documentação em português do Brasil.
2. Antes de usar uma biblioteca, verifique a versão estável atual e a licença. Registre a versão no arquivo de dependências. Se a licença está fora da lista da seção 16.1, não use a biblioteca no núcleo.
3. Não acrescente uma dependência fora da seção 16 sem um ADR.
4. Escreva o teste de contrato antes do adapter.
5. Não grave segredos em arquivos do repositório. Use `.env.example` com valores vazios.
6. Não marque uma fase como concluída se um teste falha. Relate a falha.
7. Se um requisito deste documento é tecnicamente impossível ou contraditório, pare. Explique o problema ao usuário e proponha uma alternativa.
8. Mantenha cada caso de uso independente da interface que o chama. Um teste de caso de uso não sobe FastAPI nem MCP.

---

## 24. Referências

- Langfuse: https://langfuse.com/docs
- Langfuse MCP Server: https://langfuse.com/docs/api-and-data-platform/features/mcp-server
- OpenTelemetry: https://opentelemetry.io/docs/
- Grafana Tempo: https://grafana.com/docs/tempo/latest/
- Grafana Alloy: https://grafana.com/docs/alloy/latest/
- Grafana MCP: https://grafana.com/docs/grafana/latest/ai-tools/mcp/
- Kestra: https://kestra.io/docs/architecture
- Kestra MCP: https://kestra.io/docs/ai-orchestration/mcp-server
- LangGraph: https://langchain-ai.github.io/langgraph/
- LangChain MCP Adapters: https://github.com/langchain-ai/langchain-mcp-adapters
- Model Context Protocol: https://modelcontextprotocol.io/
- MCP Inspector: https://github.com/modelcontextprotocol/inspector
- Agent Skills (padrão aberto): https://agentskills.io/
- Hermes Agent: https://github.com/NousResearch/hermes-agent
- Hermes Agent, integração MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- pgvector: https://github.com/pgvector/pgvector
- ParadeDB `pg_search`: https://github.com/paradedb/paradedb
- RAGAS: https://docs.ragas.io/
- PyO3: https://pyo3.rs/
- Maturin: https://www.maturin.rs/
- Skill de escrita: https://github.com/vladesouza7/asd-ste100-pt_BR-skill
