# Relatórios de avaliação

Esta pasta guarda os relatórios de `vlade-rag eval run`. Cada relatório registra a configuração completa da base e da execução (RF-72). O relatório não contém segredos.

## Relatórios

| Arquivo | Dataset | Configuração | Data |
|---|---|---|---|
| [`legal-ptbr-fase1.json`](legal-ptbr-fase1.json) | `legal-ptbr`, 20 perguntas | Linha de base da fase 1: busca densa e léxica com RRF, sem reranker. Embeddings `openai/text-embedding-3-small` pelo OpenRouter | 2026-11-20 |

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
