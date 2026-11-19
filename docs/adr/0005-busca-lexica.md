# ADR-0005: Busca léxica: `tsvector` padrão, `pg_search` opcional

- Status: Aceito
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D1

## Contexto

A recuperação híbrida precisa de uma busca por palavras. O `pg_search` (ParadeDB) oferece BM25 real dentro do PostgreSQL, mas usa licença AGPL-3.0 e exige uma imagem PostgreSQL personalizada. O `tsvector` é nativo do PostgreSQL, mas a pontuação `ts_rank_cd` não é BM25.

## Decisão

1. O adapter padrão de `LexicalIndex` usa `tsvector` com as configurações `vlade_pt` e `vlade_en` (`unaccent` e stemmer do idioma).
2. O `pg_search` entra como adapter opcional `bm25` na fase 3, com a imagem `vlade-postgres-bm25`.
3. O `pg_trgm` entra como adapter opcional `fuzzy` na fase 3.
4. A documentação do adapter `bm25` informa a licença AGPL-3.0 do `pg_search`.

## Alternativas avaliadas

- **`pg_search` como padrão:** melhor pontuação, mas a licença e a imagem personalizada pesam sobre todo usuário.
- **BM25 calculado na aplicação:** sem dependência externa, mas lento em bases grandes.

## Consequências

- A imagem padrão usa só extensões com a PostgreSQL License.
- O benchmark da fase 3 compara `tsvector` e `pg_search` com o mesmo dataset.
