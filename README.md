# Vlade-RAG

Framework open source de Retrieval-Augmented Generation (RAG), modular e extensível, com licença MIT.

O Vlade-RAG não é um chatbot. O Vlade-RAG entrega um núcleo reutilizável para ingestão, indexação, recuperação, geração e avaliação. Uma aplicação usa esse núcleo e troca provedores por configuração: LLM, embeddings, reranker, banco vetorial, estratégia de chunking e fontes de documentos.

> **Situação:** fase 1 (núcleo mínimo) implementada. O framework ingere documentos, busca com recuperação híbrida e responde com citações, pela biblioteca Python, pela API REST e pela CLI. Veja o [roadmap](docs/ROADMAP.md).

## Para quem

- Assistentes de atendimento e de vendas.
- Consulta a documentos de empresas.
- Assistentes jurídicos e administrativos.
- Bases de conhecimento corporativas.
- Agentes de IA que precisam de documentos internos, por MCP.
- Sistemas multi-tenant, com uma base isolada por empresa.

## Arquitetura em resumo

```text
Interfaces       API REST · Servidor MCP · CLI · Worker
Orquestração     Pipeline linear (padrão) · LangGraph · Kestra (operação)
Aplicação        Casos de uso
Domínio          Entidades e ports
Adapters         PostgreSQL/pgvector · Qdrant · Ollama · OpenAI · Gemini · OpenRouter · S3 · Valkey
Motor Rust       Normalização, chunking, tokens, hash, fusão RRF
```

O núcleo funciona como biblioteca Python, sem servidor. Os detalhes estão em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Começar a desenvolver

Requisitos:

- [uv](https://docs.astral.sh/uv/) 0.8 ou mais recente.
- Docker com Compose 2.20 ou mais recente.
- Rust estável. Opcional: só para compilar o motor nativo fora do Docker.

Instale o ambiente Python e rode os testes:

```bash
uv sync --package vlade-rag --extra api --extra cli --extra postgres --extra ollama --extra openai
uv run pytest
```

Para rodar também os testes com PostgreSQL, informe um banco de teste com um usuário superusuário:

```bash
export VLADE_TEST_DATABASE_URL=postgresql://usuario:senha@127.0.0.1:5432/postgres
uv run pytest
```

## Usar com Docker Compose

O caminho recomendado usa provedores remotos de modelos (OpenRouter, OpenCode, OpenAI ou outra API compatível com a OpenAI). Assim a máquina local roda só a API, o PostgreSQL e o Valkey, com menos de 3 GB de memória.

1. Copie `.env.example` para `.env`. Preencha `POSTGRES_PASSWORD`, `VLADE_APP_DB_PASSWORD` e `VLADE_API_KEY_PEPPER`.
2. Preencha a chave do provedor, por exemplo `OPENROUTER_API_KEY`. Em `VLADE_DEFAULT_KB_CONFIG`, troque `provedor/modelo` por um modelo de geração do provedor.
3. Suba a pilha:

   ```bash
   docker compose --profile dev up -d --build
   ```

4. Crie um tenant e uma chave de API:

   ```bash
   docker compose exec api vlade-rag tenant create minha-empresa
   docker compose exec api vlade-rag key create --tenant minha-empresa --roles admin
   ```

5. Crie uma base, envie um documento e faça uma pergunta pela API:

   ```bash
   export KEY=vrag_...
   curl -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"slug": "docs", "name": "Documentos"}' http://127.0.0.1:8000/v1/knowledge-bases
   curl -H "Authorization: Bearer $KEY" -F "file=@manual.md" \
     http://127.0.0.1:8000/v1/knowledge-bases/docs/documents
   curl -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"question": "Qual é o prazo de entrega?"}' \
     http://127.0.0.1:8000/v1/knowledge-bases/docs/query
   ```

A base usa a configuração de `VLADE_DEFAULT_KB_CONFIG`. Para mudar só uma parte numa base, envie o campo `config` com os campos que mudam, por exemplo `{"generation": {"model": "outro/modelo"}}`. Os arquivos em [`deploy/examples/`](deploy/examples/) têm exemplos completos.

A imagem padrão lê texto, Markdown e HTML. Para PDF e DOCX, instale o extra `docling`.

A documentação interativa da API fica em `http://127.0.0.1:8000/docs` fora do ambiente `prod`. Se a porta 8000 já estiver em uso, mude `VLADE_API_HOST_PORT` no `.env`.

### Modelos locais com Ollama (opcional)

O Ollama roda os modelos na própria máquina e precisa de muita memória e CPU. Para usar, suba o perfil `ollama`, defina `OLLAMA_BASE_URL=http://ollama:11434` e baixe os modelos:

```bash
docker compose --profile dev --profile ollama up -d
docker compose exec ollama ollama pull bge-m3
```

### Observabilidade (perfil `prod`)

O perfil `prod` sobe Alloy, Prometheus, Loki, Tempo e Grafana, além dos exporters de infraestrutura. A aplicação envia traces e métricas ao Alloy por OTLP quando `VLADE_OTEL__ENABLED=true`.

1. Defina `GRAFANA_ADMIN_PASSWORD` no `.env`.
2. Ligue a telemetria com `VLADE_OTEL__ENABLED=true` e `VLADE_OTEL__ENDPOINT=http://alloy:4318`.
3. Suba a pilha:

   ```bash
   docker compose --profile prod up -d
   ```

O Grafana fica em `http://127.0.0.1:3000`. A configuração, a retenção e as portas estão em [`deploy/observability/README.md`](deploy/observability/README.md). No perfil `staging`, só o Alloy sobe entre os serviços de observabilidade e envia aos backends externos.

## Estrutura do repositório

| Pasta | Conteúdo |
|---|---|
| `packages/python/` | Pacote `vlade-rag` |
| `packages/rust/vlade_rag_core/` | Motor nativo `vlade-rag-core` |
| `tests/` | Testes de unidade, contrato, integração e ponta a ponta |
| `deploy/` | Compose, Dockerfiles, PostgreSQL |
| `docs/` | Especificação, arquitetura, MCP, roadmap, ADRs e guias de operação |
| `evals/` | Datasets de avaliação |

## Documentação

| Documento | Conteúdo |
|---|---|
| [`VLADE-RAG.md`](VLADE-RAG.md) | Especificação mestre |
| [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md) | Requisitos |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Arquitetura |
| [`docs/MCP_SPEC.md`](docs/MCP_SPEC.md) | Contrato do servidor MCP |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Fases e situação |
| [`docs/adr/`](docs/adr/README.md) | Decisões de arquitetura |
| [`docs/operacao/`](docs/operacao/README.md) | Guias de implantação e operação |

## Contribuir

Leia o [`CONTRIBUTING.md`](CONTRIBUTING.md) e o [código de conduta](CODE_OF_CONDUCT.md). Para relatar uma vulnerabilidade, siga o [`SECURITY.md`](SECURITY.md).

## Licença

MIT. Veja o arquivo [`LICENSE`](LICENSE). As dependências do núcleo seguem a política de licenças do [ADR-0001](docs/adr/0001-licenca-mit.md).
