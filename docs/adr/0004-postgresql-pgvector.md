# ADR-0004: PostgreSQL com pgvector como armazenamento padrão

- Status: Aceito
- Data: 2026-11-19

## Contexto

O Vlade-RAG precisa guardar entidades, vetores e índices de texto com isolamento por tenant. Um banco único simplifica a operação e as transações.

## Decisão

1. PostgreSQL 17 é o banco padrão.
2. pgvector guarda os vetores, com índice HNSW.
3. A tabela `chunk_embeddings` tem a coluna `embedding vector` sem dimensão fixa. Cada espaço de embeddings recebe um índice HNSW parcial com expressão de dimensão fixa. Detalhes na seção 7.3 do `ARCHITECTURE.md`.
4. O acesso ao banco usa SQLAlchemy 2 (modo assíncrono), `asyncpg` e `pgvector-python`. O Alembic gerencia as migrações.
5. O Qdrant entra como adapter alternativo de `VectorIndex` na fase 5.

## Alternativas avaliadas

- **Uma tabela por espaço de embeddings:** índice simples, mas exige DDL dinâmica de tabelas e complica o RLS.
- **`psycopg` 3:** driver completo, mas usa LGPL-3.0, que a política do ADR-0001 não aceita no núcleo.
- **Banco vetorial dedicado desde o início:** melhor escala, mas duas fontes de verdade e sem transação entre o banco relacional e o banco vetorial.

## Consequências

- Uma transação publica uma versão de documento de forma atômica.
- O índice HNSW do tipo `vector` aceita até 2000 dimensões. Um modelo maior usa `halfvec`.
- A busca precisa repetir a expressão do índice parcial. O adapter centraliza essa consulta.
