# Retriever bm25 com pg_search (tarefa 3.4)

Este relatório compara o retriever `lexical` (`tsvector`) com o retriever `bm25` (`pg_search` 0.27.0, ADR-0022). Ele mede a qualidade no mesmo dataset (ADR-0005) e o critério de aceite do ADR-0020: o p95 da busca lexical com 100 mil chunks fica abaixo de 300 ms.

**Resumo.**

- **O critério do ADR-0020 foi cumprido.** Com 102.253 chunks, o p95 do `bm25` é de 59,5 ms. O p95 do `tsvector` é de 6.813 ms na mesma base.
- **O `bm25` melhora a qualidade da busca lexical.** No `legal-ptbr-v2`, o MRR sobe de 0,512 para 0,686. No `legal-ptbr`, o Recall@10 sobe de 0,85 para 1,00.
- **Com erros de digitação, o Recall@10 cai** de 0,807 para 0,734. O MRR sobe de 0,454 para 0,539.
- **Um filtro de metadados custa caro no `bm25`.** O filtro não está no índice, então a consulta lê a linha de cada chunk que casa com a pergunta. Uma consulta medida levou cerca de 300 ms com 70 mil chunks que casam (limitação L18).

## Ambiente

| Item | Valor |
|---|---|
| Máquina | 4 CPUs, 7,7 GB de RAM, WSL2 no Windows. A mesma do benchmark da tarefa 3.10 |
| PostgreSQL | 17 na imagem `vlade-postgres-bm25`, em container Docker com limite de **1 GiB** de memória |
| `pg_search` | 0.27.0 |
| Python | 3.12.3, sem o motor Rust |
| Provedores | Nenhum. A qualidade usa só os retrievers lexicais. A base sintética usa embeddings `hashing` |
| Caches | Desligados. Toda consulta é fria |

## Qualidade

O comando é `vlade-rag eval run <base> --dataset <arquivo> --retrievers lexical` e depois `--retrievers bm25`. As bases `legal-ptbr` (124 chunks) e `legal-ptbr-v2` (184 chunks) são cópias das bases dos relatórios `fase3-consulta-fuzzy` e `fase3-dataset-v2`. Os chunks são os mesmos. Cada retriever roda sozinho, sem a busca vetorial e sem reranker.

| Dataset | Retriever | Recall@1 | Recall@10 | MRR | NDCG@10 |
|---|---|---|---|---|---|
| `legal-ptbr` (20 perguntas) | `lexical` | 0,500 | 0,850 | 0,643 | 0,686 |
| | `bm25` | **0,650** | **1,000** | **0,766** | **0,822** |
| `legal-ptbr-v2` (109 perguntas) | `lexical` | 0,307 | 0,844 | 0,512 | 0,582 |
| | `bm25` | **0,541** | **0,862** | **0,686** | **0,716** |
| `legal-ptbr-v2` com erros de digitação | `lexical` | 0,274 | **0,807** | 0,454 | 0,524 |
| | `bm25` | **0,404** | 0,734 | **0,539** | **0,572** |

No `legal-ptbr-v2`, o ganho aparece nos dois estilos de pergunta. O MRR das 74 perguntas formais sobe de 0,573 para 0,778. O MRR das 35 perguntas coloquiais sobe de 0,384 para 0,491.

Com erros de digitação, o `bm25` acha menos documentos entre os 10 primeiros. O `tsvector` junta as palavras da pergunta com OU, e o `bm25` também. Uma explicação provável é a diferença de stemmer e de stop words entre os dois, mas ninguém examinou as perguntas que pioraram. O retriever `fuzzy` (ADR-0019) trata os erros de digitação.

## Latência com 100 mil chunks

A base `bench-hash` é sintética, como na tarefa 3.10: documentos de 100 páginas montados com os documentos do `legal-ptbr-v2`, até 102.253 chunks. Os embeddings `hashing` têm 64 dimensões, não 1.024. A busca lexical não usa os embeddings, então a mudança não afeta a medida lexical. A busca vetorial fica mais rápida do que na tarefa 3.10 e não é comparável.

Latência em milissegundos, 100 consultas depois de 3 de aquecimento:

| Retrievers | Consultas ao mesmo tempo | p50 | p95 | Etapa lexical (p95) | Vazão (consultas/s) |
|---|---|---|---|---|---|
| `lexical` | 1 | 4.101 | 6.813 | 6.801 | 0,24 |
| `bm25` | 1 | 47 | **60** | 51 | 20,8 |
| `dense`, `lexical` | 1 | 3.333 | 6.558 | 6.549 | 0,28 |
| `dense`, `bm25` | 1 | 55 | **66** | 57 | 18,4 |
| `dense`, `bm25` | 4 | 155 | 233 | 211 | 24,4 |

Fatos sobre a medida:

- **O `pg_search` devolve só os melhores.** O plano usa `TopKScanExecState`: o índice classifica os chunks que casam e devolve só os 50 melhores. O `tsvector` classifica todos os chunks que casam (limitação L16). Na primeira pergunta do dataset, 70.156 chunks casam.
- **A primeira versão da função levou 296 ms e 319 ms de p95 em duas execuções.** A função chamava o filtro de metadados mesmo sem filtro, e a chamada lia a linha de cada chunk que casa. Com o `EXPLAIN ANALYZE`, a mesma consulta levou 300 ms com a chamada e de 26 a 46 ms sem ela. A versão final só põe o filtro na consulta quando ele existe.
- **Memória.** O container do PostgreSQL usou 629 MB de 1 GiB no fim da medida.

## Índice e ingestão

| Medida | Valor |
|---|---|
| Tempo de criação do índice com 102.253 chunks | 47,3 s, com 2 workers paralelos |
| Tamanho do índice `bm25` | 121 MB (três campos de texto) |
| Tamanho do índice `tsvector` (`chunks_tsv_idx`) | 56 MB |
| Ingestão de 25 documentos de 100 páginas sem o índice `bm25` | 99,3 páginas por segundo (25,3 s) |
| Ingestão de 25 documentos de 100 páginas com o índice `bm25` | 117,6 páginas por segundo (21,3 s) |

As duas medidas de ingestão têm só 25 documentos cada. A ingestão com o índice foi mais rápida, o que mostra que a variação entre execuções é maior que o custo do índice. Esta medida não mostra custo do índice na ingestão, mas também não prova que ele é zero.

## Limites da medida

- **A base sintética repete 150 documentos.** Toda palavra comum casa com uma fração enorme dos chunks. Isso é o pior caso para o `tsvector` e um caso pesado para o `bm25`.
- **Uma máquina, sem isolamento.** A latência varia entre execuções.
- **Sem a base de 1 milhão de chunks.** A meta do RNF-01 é para 1 milhão de chunks, e a base não cabe nesta máquina (ADR-0020).
- **A qualidade com a busca vetorial e com o reranker não foi medida.** O limite de gasto da chave do OpenRouter acabou. As medidas desta pasta não chamam provedor.

## Como repetir

Gere a imagem e use um servidor com ela:

```bash
docker build -f deploy/postgres/Dockerfile.bm25 -t vlade-postgres-bm25:17 deploy/postgres
```

Use uma chave de administrador (`VLADE_API_KEY`) e as variáveis `VLADE_*` da CLI. Rode com `uv run`:

```bash
# Qualidade
vlade-rag eval run legal-ptbr-v2 --dataset evals/datasets/legal-ptbr-v2/questions.jsonl --retrievers bm25

# Base sintética e latência
python scripts/benchmarks/bench.py ingest --kb bench-hash --docs evals/datasets/legal-ptbr-v2/docs \
  --replicas 520 --pages-per-document 100 --concurrency 2 --dimension 64
python scripts/benchmarks/bench.py search --kb bench-hash \
  --dataset evals/datasets/legal-ptbr-v2/questions.jsonl --n 100 --retrievers bm25
```

A primeira busca `bm25` cria o índice. Com 100 mil chunks, a criação leva cerca de 50 s e bloqueia as escritas em `chunks`.
