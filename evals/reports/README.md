# Relatórios de avaliação

Esta pasta guarda os relatórios de `vlade-rag eval run`. Cada relatório registra a configuração completa da base e da execução (RF-72). O relatório não contém segredos.

## Relatórios

| Arquivo | Dataset | Configuração | Data |
|---|---|---|---|
| [`legal-ptbr-fase1.json`](legal-ptbr-fase1.json) | `legal-ptbr`, 20 perguntas | Linha de base da fase 1: busca densa e léxica com RRF, sem reranker. Embeddings `openai/text-embedding-3-small` pelo OpenRouter | 2026-11-20 |
| [`legal-ptbr-fase3-cohere-rerank-v3.5.json`](legal-ptbr-fase3-cohere-rerank-v3.5.json) | `legal-ptbr`, 20 perguntas | Linha de base mais reranker `cohere/rerank-v3.5` pelo OpenRouter, 50 candidatos | 2026-11-20 |
| [`legal-ptbr-fase3-cohere-rerank-4-fast.json`](legal-ptbr-fase3-cohere-rerank-4-fast.json) | `legal-ptbr`, 20 perguntas | Linha de base mais reranker `cohere/rerank-4-fast` | 2026-11-20 |
| [`legal-ptbr-fase3-mongodb-rerank-2.5.json`](legal-ptbr-fase3-mongodb-rerank-2.5.json) | `legal-ptbr`, 20 perguntas | Linha de base mais reranker `mongodb/rerank-2.5` (Voyage) | 2026-11-20 |
| [`legal-ptbr-fase3-qwen3-reranker-8b.json`](legal-ptbr-fase3-qwen3-reranker-8b.json) | `legal-ptbr`, 20 perguntas | Linha de base mais reranker `qwen/qwen3-reranker-8b` | 2026-11-20 |
| [`legal-ptbr-fase3-nvidia-nemotron-rerank-8b-free.json`](legal-ptbr-fase3-nvidia-nemotron-rerank-8b-free.json) | `legal-ptbr`, 20 perguntas | Linha de base mais reranker `nvidia/nemotron-3.5-rerank-8b:free` | 2026-11-20 |

## Reranker por API (tarefa 3.1)

Os cinco modelos dão o mesmo resultado. A tabela compara esse resultado com a linha de base:

| Métrica | Linha de base | Com reranker (os cinco modelos) |
|---|---|---|
| Recall@1 | 0,70 | 0,95 |
| Recall@3 | 0,85 | 1,00 |
| Recall@10 | 1,00 | 1,00 |
| MRR | 0,786 | 0,975 |
| NDCG@10 | 0,838 | 0,982 |

- A pergunta 20 passou da posição 9 para a posição 1.
- A pergunta 5 passou da posição 1 para a posição 2. Os modelos põem o `lgpd-026` (artigo 41) antes do `lgpd-003` (artigo 5). O `lgpd-026` também responde à pergunta, mas o gabarito lista só o `lgpd-003`.
- O dataset não separa os modelos: a ordem dos 10 primeiros documentos muda em todas as perguntas, mas o primeiro documento relevante fica na mesma posição. O custo e a latência de cada modelo estão no ADR-0018.
- Com o reranker ligado, o avaliador eleva `top_n` a 50 (o número de trechos buscados). O relatório grava esse valor em `knowledge_base_config.retrieval.rerank.top_n`.

Para repetir um modelo:

```bash
vlade-rag eval run <base> --dataset evals/datasets/legal-ptbr/questions.jsonl --k 10 \
  --rerank-model cohere/rerank-v3.5 --output evals/reports/<nome>.json
```

A opção `--rerank-provider` escolhe o provedor (padrão `openrouter`). A chave do provedor vem de `VLADE_PROVIDERS__OPENROUTER__API_KEY`.

## Transformadores de consulta e fuzzy (tarefas 3.2 e 3.3)

A pasta [`fase3-consulta-fuzzy/`](fase3-consulta-fuzzy/) guarda 30 relatórios: 3 datasets e 10 configurações. O nome do arquivo é `<dataset>.<configuração>.json`.

| Dataset | Arquivo de perguntas |
|---|---|
| `original` | `questions.jsonl` |
| `typos` | `questions-typos.jsonl` (duas letras trocadas em duas palavras longas) |
| `paraphrase` | `questions-paraphrase.jsonl` (palavras do dia a dia, escritas à mão) |

| Configuração | O que muda |
|---|---|
| `base` | Denso e léxico, sem reranker |
| `fuzzy` | `--retrievers dense,lexical,fuzzy` |
| `rewrite`, `multi`, `hyde` | `--query-transform rewrite`, `multi_query` e `hyde` |
| `rerank` | `--rerank-model mongodb/rerank-2.5` |
| `rerank-fuzzy`, `rerank-rewrite`, `rerank-multi`, `rerank-hyde` | O reranker com cada técnica |

MRR de cada configuração:

| Configuração | `original` | `typos` | `paraphrase` |
|---|---|---|---|
| `base` | 0,786 | 0,729 | 0,498 |
| `fuzzy` | 0,841 | 0,754 | 0,485 |
| `rewrite` | 0,756 | 0,756 | 0,596 |
| `multi` | 0,744 | 0,769 | 0,622 |
| `hyde` | 0,854 | 0,775 | 0,681 |
| `rerank` e as quatro combinações com reranker | 0,975 | 0,975 | 0,950 |

- Com o reranker, as quatro técnicas não mudam o resultado.
- Sem o reranker, o HyDE é a melhor transformação nos três datasets.
- Recall@10, NDCG@10 e as outras métricas estão nos relatórios. O ADR-0019 traz a tabela com o Recall@10.
- A geração dos relatórios usou o `tencent/hy4-flash` para as transformações e o `mongodb/rerank-2.5` para o reranker, os dois pelo OpenRouter.

Para repetir uma configuração:

```bash
vlade-rag eval run <base> --dataset evals/datasets/legal-ptbr/questions-paraphrase.jsonl --k 10 \
  --query-transform hyde --output evals/reports/<nome>.json
```

## Dataset `legal-ptbr-v2`

A pasta [`fase3-dataset-v2/`](fase3-dataset-v2/) guarda 15 relatórios do dataset [`legal-ptbr-v2`](../datasets/legal-ptbr-v2/README.md) (109 perguntas). O nome do arquivo é `<perguntas>.<configuração>.json`: `orig` usa `questions.jsonl` e `typos` usa `questions-typos.jsonl`.

| Arquivo | Configuração |
|---|---|
| `orig.base.json`, `typos.base.json` | Denso e léxico, sem reranker |
| `orig.fuzzy.json`, `typos.fuzzy.json` | `--retrievers dense,lexical,fuzzy` |
| `orig.hyde.json` | `--query-transform hyde` |
| `orig.rewrite.json` | `--query-transform rewrite` |
| `orig.multi.json` | `--query-transform multi_query` |
| `orig.mongodb.json`, `typos.mongodb.json` | `--rerank-model mongodb/rerank-2.5` |
| `orig.cohere4fast.json` | `--rerank-model cohere/rerank-4-fast` |
| `orig.qwen3.json` | `--rerank-model qwen/qwen3-reranker-8b` |
| `orig.mongodb-fuzzy.json`, `orig.mongodb-hyde.json`, `orig.mongodb-rewrite.json`, `orig.mongodb-multi.json` | O reranker `mongodb/rerank-2.5` com cada técnica |

As tabelas de resultado estão no README do dataset. O resumo por grupo e por estilo sai do script `scripts/datasets/summarize_by_group.py`.

## Benchmark de latência e de vazão (tarefa 3.10)

A pasta [`fase3-benchmark/`](fase3-benchmark/) guarda 40 relatórios do `scripts/benchmarks/bench.py` e o [README](fase3-benchmark/README.md) com o método, o ambiente, as tabelas e as limitações.

| Subpasta | O que tem |
|---|---|
| `ingestao/` | Vazão de ingestão por tamanho de documento e por número de jobs |
| `busca/` | Latência da busca na base real: sem reranker, com três rerankers e com as três transformações de consulta |
| `escala/` | Busca em uma base sintética de 6 mil a 104 mil chunks, a ingestão que a cresceu e o primeiro token |

## Critério de aceite da fase 3 (tarefas 3.7 e 3.8)

A pasta [`fase3-ragas/`](fase3-ragas/) compara a configuração da fase 1 com a da fase 3, com as métricas de recuperação e as quatro métricas do RAGAS. O [README](fase3-ragas/README.md) tem as tabelas, o juiz usado e os limites da medida.

## Retriever bm25 (tarefa 3.4)

A pasta [`fase3-bm25/`](fase3-bm25/) guarda 13 relatórios e o [README](fase3-bm25/README.md). Os arquivos `qualidade.*` comparam os retrievers `lexical` e `bm25` em três conjuntos de perguntas. Os arquivos `busca.*` e `ingestao.*` medem a latência e a ingestão em uma base sintética de 102 mil chunks.

## Linha de base da fase 1

| Métrica | Valor |
|---|---|
| Recall@1 | 0,70 |
| Recall@3 | 0,85 |
| Recall@5 | 0,95 |
| Recall@10 | 1,00 |
| Precision@1 | 0,70 |
| MRR | 0,786 |
| NDCG@10 | 0,838 |

Em 6 das 20 perguntas, o documento certo não vem em primeiro lugar. A pergunta 20 ("O que é fornecedor segundo o CDC?") traz o documento certo na posição 9. O `vlade_query` usa só os 8 primeiros trechos, então essa pergunta recebe a resposta "Não encontrei essa informação" (limitação L1 do roadmap).

A fase 3 compara a sua melhor configuração com esta linha de base no mesmo dataset.

## Como a medida funciona

- A medida é por documento. O avaliador busca até 5 trechos para cada posição do corte K e agrupa os trechos por documento. Cada documento ocupa a posição do seu melhor trecho.
- O dataset diz quais documentos respondem a cada pergunta (`relevant_documents`, os nomes dos arquivos). Recall@K e NDCG@K usam todos os documentos do dataset, inclusive os que a busca não achou.
- A avaliação não usa LLM. O custo é só o embedding das perguntas.

## Como repetir

```bash
vlade-rag eval run <base> --dataset evals/datasets/legal-ptbr/questions.jsonl --k 10 \
  --output evals/reports/<nome>.json
```

O comando exige a chave de um administrador (`VLADE_API_KEY`) e a base com os 100 documentos do dataset ingeridos. Os valores mudam com o modelo de embedding, com o `chunking` e com a configuração de recuperação da base.
