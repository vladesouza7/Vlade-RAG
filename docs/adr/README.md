# Registros de decisão de arquitetura (ADR)

Cada arquivo registra uma decisão. Um ADR aceito não muda. Para mudar uma decisão, crie um ADR novo e marque o ADR antigo como `Substituído por ADR-NNNN`.

| ADR | Título | Status | Decisão no VLADE-RAG.md |
|---|---|---|---|
| [0001](0001-licenca-mit.md) | Licença MIT e política de licenças das dependências | Aceito | D7 |
| [0002](0002-arquitetura-ports-adapters.md) | Clean Architecture com ports e adapters | Aceito | — |
| [0003](0003-divisao-rust-python.md) | Divisão entre Rust e Python e distribuição dos pacotes | Aceito | — |
| [0004](0004-postgresql-pgvector.md) | PostgreSQL com pgvector como armazenamento padrão | Aceito. Item 4 substituído pelo ADR-0016 | — |
| [0005](0005-busca-lexica.md) | Busca léxica: `tsvector` padrão, `pg_search` opcional | Aceito. Item 2 complementado pelo ADR-0022 | D1 |
| [0006](0006-armazenamento-de-objetos.md) | Armazenamento de objetos pela API S3 | Aceito. Item 3 substituído pelo ADR-0017 | D2 |
| [0007](0007-cache-valkey.md) | Valkey como cache padrão | Aceito | D3 |
| [0008](0008-modelos-padrao.md) | Modelos padrão de embeddings e de reranking | Aceito. Item 2 complementado pelo ADR-0018 | D4, D5 |
| [0009](0009-idiomas-do-projeto.md) | Idiomas do código e da documentação | Aceito | — |
| [0010](0010-extracao-docling.md) | Docling para extração de documentos | Aceito | D6 |
| [0011](0011-orquestracao-kestra-langgraph.md) | Kestra para operação, LangGraph para consulta, fila no PostgreSQL | Aceito | — |
| [0012](0012-multi-tenancy-rls.md) | Isolamento de tenants com Row-Level Security | Aceito | — |
| [0013](0013-mcp-qualquer-cliente.md) | MCP como interface de primeira classe para qualquer cliente | Aceito | D8 |
| [0014](0014-sem-human-in-the-loop-v1.md) | Sem human-in-the-loop na versão 1 | Aceito | D9 |
| [0015](0015-observabilidade.md) | Observabilidade com OpenTelemetry, Langfuse e LGTM | Aceito | — |
| [0016](0016-asyncpg-e-migracoes-sql.md) | asyncpg e migrações em SQL (substitui o item 4 do ADR-0004) | Aceito | — |
| [0017](0017-minio-deixa-de-ser-o-servico-s3-de-exemplo.md) | O MinIO deixa de ser o serviço S3 de exemplo (substitui o item 3 do ADR-0006) | Aceito. Itens 3 e 4 completados pelo ADR-0021 | — |
| [0018](0018-reranker-por-api-primeiro.md) | Reranker por API primeiro, reranker local como extra opcional (complementa o item 2 do ADR-0008) | Aceito | — |
| [0019](0019-transformadores-de-consulta-e-retriever-fuzzy.md) | Transformadores de consulta e retriever fuzzy (complementa o item 3 do ADR-0005 e o ADR-0018) | Aceito | — |
| [0020](0020-metas-de-latencia-e-de-vazao.md) | Metas de latência e de vazão depois do benchmark da fase 3 | Proposto | — |
| [0021](0021-rustfs-servico-s3-de-exemplo.md) | RustFS é o serviço S3 de exemplo (completa os itens 3 e 4 do ADR-0017) | Aceito | D2 |
| [0022](0022-retriever-bm25-com-pg-search.md) | Retriever bm25 com pg_search (complementa o item 2 do ADR-0005 e o item 2 do ADR-0020) | Aceito | D1 |

## Modelo

```markdown
# ADR-NNNN: <título>
- Status: Proposto | Aceito | Substituído por ADR-NNNN
- Data: AAAA-MM-DD
## Contexto
## Decisão
## Alternativas avaliadas
## Consequências
```
