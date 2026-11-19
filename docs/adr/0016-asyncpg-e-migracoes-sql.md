# ADR-0016: asyncpg e migrações em SQL

- Status: Aceito
- Data: 2026-11-19
- Substitui: o item 4 do ADR-0004 (SQLAlchemy e Alembic)

## Contexto

O ADR-0004 previa SQLAlchemy 2, `asyncpg` e Alembic. Na implementação da fase 1, três fatos apareceram:

1. O índice HNSW parcial por espaço de embeddings, as políticas de RLS e as funções `SECURITY DEFINER` exigem SQL escrito à mão. O SQLAlchemy não simplifica essas partes.
2. O Alembic roda as migrações com um driver síncrono. O driver síncrono comum, `psycopg`, usa LGPL-3.0, e o ADR-0001 não aceita essa licença no núcleo.
3. Cada camada a mais aumenta as dependências do extra `postgres`.

## Decisão

1. Os adapters PostgreSQL usam `asyncpg` diretamente, com SQL parametrizado (`$1`, `$2`).
2. O pacote `pgvector` registra o codec do tipo `vector` no `asyncpg`.
3. As migrações são arquivos SQL numerados em `vlade_rag/knowledge/postgres/migrations/` (`0001_initial.sql`). O comando `vlade-rag db upgrade` aplica cada arquivo uma vez, em ordem, dentro de uma transação, e registra o arquivo na tabela `vlade_schema_migrations`.
4. A migração usa a credencial de dono do banco (`VLADE_DATABASE__OWNER_URL`). Depois das migrações, o comando cria ou atualiza o papel de login da aplicação a partir de `VLADE_DATABASE__URL` e põe esse papel no grupo `vlade_app_group`.
5. As operações que atravessam tenants usam funções `SECURITY DEFINER`. O dono dessas funções é `vlade_definer`, um papel sem login. As operações são: autenticação por chave, busca de tenant por slug, reserva de job, renovação de prazo e devolução de jobs vencidos à fila.
6. A criação do índice HNSW de cada espaço de embeddings usa uma função `SECURITY DEFINER` com o dono da tabela, com argumentos tipados e conferidos.

## Alternativas avaliadas

- **SQLAlchemy Core com Alembic:** ecossistema conhecido, mas pede um driver síncrono para as migrações e não ajuda nas partes de SQL específico.
- **Alembic com driver assíncrono:** possível com `run_sync`, mas mantém a dependência do SQLAlchemy sem ganho para este projeto.

## Consequências

- O extra `postgres` instala só `asyncpg` (Apache-2.0) e `pgvector` (MIT).
- Uma migração nova é um arquivo SQL novo. Uma migração não muda depois de publicada.
- A primeira migração precisa de um papel que crie papéis e mude o dono de funções. No Compose, o papel `vlade_owner` é superusuário.
