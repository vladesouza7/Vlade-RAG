# Vlade-RAG

Framework open source de Retrieval-Augmented Generation (RAG), modular e extensível, com licença MIT.

O Vlade-RAG não é um chatbot. O Vlade-RAG entrega um núcleo reutilizável para ingestão, indexação, recuperação, geração e avaliação. Uma aplicação usa esse núcleo e troca provedores por configuração: LLM, embeddings, reranker, banco vetorial, estratégia de chunking e fontes de documentos.

> **Situação:** fase 0 (fundação). O repositório tem a especificação, a arquitetura, a estrutura do código, a CI e o ambiente de desenvolvimento. As funções de RAG chegam na fase 1. Veja o [roadmap](docs/ROADMAP.md).

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
uv sync --package vlade-rag --extra api --extra cli
uv run pytest
```

Suba o perfil `dev` (API, PostgreSQL e Valkey):

```bash
cp .env.example .env          # preencha POSTGRES_PASSWORD
docker compose --profile dev up --build
curl http://127.0.0.1:8000/health/live
```

Se a porta 8000 já estiver em uso, mude `VLADE_API_HOST_PORT` no `.env`.

## Estrutura do repositório

| Pasta | Conteúdo |
|---|---|
| `packages/python/` | Pacote `vlade-rag` |
| `packages/rust/vlade_rag_core/` | Motor nativo `vlade-rag-core` |
| `tests/` | Testes de unidade, contrato, integração e ponta a ponta |
| `deploy/` | Compose, Dockerfiles, PostgreSQL |
| `docs/` | Especificação, arquitetura, MCP, roadmap e ADRs |
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

## Contribuir

Leia o [`CONTRIBUTING.md`](CONTRIBUTING.md) e o [código de conduta](CODE_OF_CONDUCT.md). Para relatar uma vulnerabilidade, siga o [`SECURITY.md`](SECURITY.md).

## Licença

MIT. Veja o arquivo [`LICENSE`](LICENSE). As dependências do núcleo seguem a política de licenças do [ADR-0001](docs/adr/0001-licenca-mit.md).
