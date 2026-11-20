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
