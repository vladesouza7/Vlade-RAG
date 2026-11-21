# ADR-0022: Retriever bm25 com pg_search

- Status: Aceito
- Data: 2026-11-21
- Complementa o item 2 do ADR-0005 e o item 2 do ADR-0020
- Decisão no VLADE-RAG.md: D1

## Contexto

O item 2 do ADR-0005 define o `pg_search` (ParadeDB) como adapter opcional `bm25` na fase 3, com a imagem `vlade-postgres-bm25`. O ADR-0020 deu à tarefa 3.4 um critério de aceite: o p95 da busca lexical com 100 mil chunks fica abaixo de 300 ms no mesmo benchmark. O índice `tsvector` atual classifica todos os chunks que casam com a pergunta e leva 7,939 s no p95 com 104 mil chunks (limitação L16).

Os testes de 2026-11-21 com o `pg_search` 0.27.0 e o PostgreSQL 17 mostraram quatro fatos:

1. A versão 0.27 exige `shared_preload_libraries = 'pg_search'`. Sem isso, `CREATE EXTENSION` falha.
2. Um índice `bm25` aceita vários tokenizadores para a mesma coluna, cada um com um nome (`alias`). O tokenizador `pdb.unicode_words` aceita stemmer, stop words e `ascii_folding`, que tira os acentos.
3. O `pg_search` executa no índice os filtros de igualdade sobre campos do índice e devolve só os `top_k` melhores (`TopKScanExecState`). Um filtro que não está no índice, por exemplo sobre `metadata`, roda como filtro sobre a linha, dentro do mesmo scan.
4. O `pg_search` não usa o próprio scan quando uma política de Row-Level Security vale para a consulta. O planner usa outro índice, e a função `pdb.score` falha. O papel `vlade_app` sempre tem a política `tenant_isolation` (ADR-0012).

## Decisão

1. **Imagem.** `deploy/postgres/Dockerfile.bm25` gera a `vlade-postgres-bm25`: a imagem padrão mais o pacote Debian do `pg_search` 0.27.0, com o SHA-256 conferido, e `shared_preload_libraries = 'pg_search'` no `CMD`. No Compose, as variáveis `POSTGRES_DOCKERFILE` e `POSTGRES_IMAGE` trocam a imagem. A imagem padrão não muda.
2. **Índice.** O índice `chunks_bm25_idx` tem três campos de texto: `text_pt` e `text_en`, com stemmer, stop words e `ascii_folding`, e `text_simple`, só com `ascii_folding`. O idioma da base escolhe o campo, como no `tsvector`. O índice também guarda `tenant_id`, `knowledge_base_id` e `is_published`, para os filtros rodarem no índice. A coluna `metadata` fica fora do índice.
3. **Criação na primeira busca.** A função `vlade_ensure_bm25_index()` (migração 0003) cria a extensão, se a imagem tiver o pacote, e o índice. O adapter chama a função na primeira busca `bm25` do processo, como o retriever fuzzy (ADR-0019). Sem o pacote, o retriever devolve `invalid_argument` com o nome da imagem.
4. **Busca fora da RLS, com o tenant na consulta.** A busca roda na função `vlade_bm25_search()`, do papel `vlade_definer`, com `SECURITY DEFINER`. Uma política nova (`definer_read`) deixa esse papel ler `chunks`. A função lê o tenant de `app.tenant_id`, o mesmo valor que a política `tenant_isolation` lê, e põe o tenant na consulta como literal. Sem `app.tenant_id`, o resultado é vazio. A função aceita só três nomes de campo e põe a pergunta e os identificadores na consulta com `format('%L')`.
5. **Filtros de metadados.** A função `vlade_metadata_matches()` aplica o filtro com a mesma semântica de `filter_sql`. O adapter envia o filtro como JSON (`filter_json`). O filtro entra na consulta só quando existe, porque ele lê a linha de cada chunk que casa.
6. **Licença.** O `pg_search` usa AGPL-3.0. Ele roda dentro do processo do PostgreSQL, sem modificação, e não entra no pacote Python (seção 16.1 do `VLADE-RAG.md`, item 4). O Dockerfile, o `.env.example` e o `ARCHITECTURE.md` informam a licença.
7. **Testes.** `tests/integration/test_bm25.py` roda com o adapter em memória e com o PostgreSQL com `pg_search` (`VLADE_TEST_BM25_DATABASE_URL`). O job `BM25 retriever (pg_search)` da CI gera a imagem e roda esses testes.

## Alternativas avaliadas

- **Usar o scan do `pg_search` sob a RLS:** o `pg_search` 0.27 não usa o scan próprio nesse caso. Recusado até uma versão aceitar.
- **Desligar a RLS para o papel da aplicação na busca:** quebra a defesa em profundidade do ADR-0012 em todas as consultas. Recusado.
- **Imagem `paradedb/paradedb`:** traz o `pg_search` e o pgvector, mas muda a base da imagem padrão e acrescenta outras extensões. Recusado. A imagem `vlade-postgres-bm25` só acrescenta o `pg_search` à imagem padrão.
- **Um índice por idioma (índices parciais):** o `pg_search` aceita vários campos com nomes diferentes no mesmo índice. Um índice só fica mais simples de criar e de manter.
- **Pôr `metadata` no índice:** o filtro `@>` não roda no índice. Ele roda como filtro sobre a linha nos dois casos.

## Consequências

- O retriever `bm25` existe e é opcional. O padrão continua `[dense, lexical]`.
- A RLS não protege a busca `bm25`. A proteção é a função `vlade_bm25_search()`, que lê o mesmo `app.tenant_id` da política. O teste de isolamento do retriever confere isso.
- A primeira busca `bm25` cria o índice e bloqueia as escritas em `chunks` enquanto a criação roda, como no fuzzy (limitação L14).
- Cada escrita em `chunks` também atualiza o índice `bm25`. A seção de medidas mostra o custo na ingestão.
- Uma versão nova do `pg_search` exige mudar a versão e os dois SHA-256 no Dockerfile. O job da CI roda os testes com a versão nova.

- Uma busca com filtro de metadados lê a linha de cada chunk que casa com a pergunta. Ela custa cerca de 300 ms em uma consulta com 70 mil chunks que casam (limitação L18).

## Medidas

O relatório completo está em `evals/reports/fase3-bm25/README.md`. A base sintética tem 102.253 chunks, e o container do PostgreSQL tem 1 GiB.

| Medida | `tsvector` (`lexical`) | `pg_search` (`bm25`) |
|---|---|---|
| p95 da busca lexical sozinha | 6.813 ms | 60 ms |
| p95 de `dense` com o retriever lexical | 6.558 ms | 66 ms |
| MRR no `legal-ptbr-v2` (109 perguntas) | 0,512 | 0,686 |
| Recall@10 no `legal-ptbr` (20 perguntas) | 0,85 | 1,00 |
| Recall@10 no `legal-ptbr-v2` com erros de digitação | 0,807 | 0,734 |
| Tamanho do índice | 56 MB | 121 MB |

O critério de aceite do ADR-0020 para a tarefa 3.4 (p95 lexical abaixo de 300 ms com 100 mil chunks) está cumprido. A criação do índice levou 47 s.
