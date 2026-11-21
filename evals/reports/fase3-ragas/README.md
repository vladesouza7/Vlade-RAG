# Fase 1 contra fase 3: recuperação e respostas (critério de aceite da fase 3)

O critério de aceite da fase 3 pede um relatório que compare a configuração da fase 1 com a configuração da fase 3 no mesmo dataset, com Recall@10 e faithfulness. Este relatório cumpre o critério com o dataset `legal-ptbr`. O `legal-ptbr-v2` ficou incompleto: o limite de gasto da chave do OpenRouter acabou na última etapa.

**Resumo.**

- **O reranker melhora a recuperação.** No `legal-ptbr`, o MRR sobe de 0,786 para 0,975 e o Recall@1 de 0,70 para 0,95. No `legal-ptbr-v2`, o MRR sobe de 0,740 para 0,959.
- **O Recall@10 já era alto na fase 1.** Ele fica em 1,000 no `legal-ptbr` e sobe de 0,979 para 1,000 no `legal-ptbr-v2`.
- **A faithfulness fica no mesmo nível.** No `legal-ptbr`, ela é de 0,950 na fase 1 e de 0,938 na fase 3. A queda vem de uma pergunta em que o juiz errou (ver "Erro do juiz"). Sem essa pergunta, a fase 3 tem 0,987.
- **O contexto fica mais preciso.** A context precision sobe de 0,720 para 0,996, e todas as 20 respostas da fase 3 têm citação.

## Configurações

| Item | Fase 1 | Fase 3 |
|---|---|---|
| Retrievers | `dense`, `lexical`, fusão RRF | Os mesmos |
| Reranker | Nenhum | `mongodb/rerank-2.5` pelo OpenRouter, 50 candidatos |
| Motor de consulta | `pipeline` | `pipeline` |
| Embeddings da base | `openai/text-embedding-3-small` | O mesmo |
| LLM da base | `tencent/hy4-flash` | O mesmo |

A avaliação das respostas usa o RAGAS 0.4.4 (ADR-0025). O juiz é o `deepseek/deepseek-v4.1-flash`, com o raciocínio desligado e 8192 tokens de saída. Os embeddings do answer relevancy são o `openai/text-embedding-3-small`. Os dois passam pelo OpenRouter. As duas fases usam o mesmo juiz, então a comparação entre elas vale. Uma comparação com outro juiz não vale.

## Resultados

### `legal-ptbr` (20 perguntas, 100 documentos)

| Métrica | Fase 1 | Fase 3 |
|---|---|---|
| Recall@1 | 0,700 | **0,950** |
| Recall@10 | 1,000 | 1,000 |
| MRR | 0,786 | **0,975** |
| NDCG@10 | 0,837 | **0,982** |
| Faithfulness | 0,950 | 0,938 (0,987 sem o erro do juiz) |
| Answer relevancy | 0,855 | 0,872 |
| Context precision | 0,720 | **0,996** |
| Context recall | 0,925 | **1,000** |
| Respostas com citação (`grounded`) | 0,95 | **1,00** |

Todas as perguntas receberam as quatro métricas nas duas fases. O juiz não teve erro.

### `legal-ptbr-v2` (109 perguntas, 150 documentos)

| Métrica | Fase 1 | Fase 3 |
|---|---|---|
| Recall@1 | 0,560 | **0,867** |
| Recall@10 | 0,979 | **1,000** |
| MRR | 0,740 | **0,959** |
| NDCG@10 | 0,788 | **0,969** |
| Faithfulness | 0,904 | Sem medida |
| Answer relevancy | 0,757 | Sem medida |
| Context precision | 0,697 | Sem medida |
| Context recall | 0,933 | Sem medida |
| Respostas com citação (`grounded`) | 0,927 | Sem medida |

As respostas da fase 3 não foram medidas: a chave do OpenRouter chegou ao limite total de US$ 5,00 nessa etapa. Na fase 1, 9 perguntas tiveram faithfulness abaixo de 0,5 e 8 respostas ficaram sem citação.

## O que mudou entre as fases no `legal-ptbr`

| Pergunta | Fase 1 | Fase 3 |
|---|---|---|
| "O que é fornecedor segundo o CDC?" | Sem citação, faithfulness 0,0 | Com citação, faithfulness 1,0 |
| "Em quais hipóteses o tratamento de dados pessoais pode ser realizado?" | Faithfulness 1,0 | Faithfulness 0,0 (erro do juiz) |
| "Qual é o prazo para desistir de uma compra feita fora do estabelecimento?" | Faithfulness 1,0 | Faithfulness 0,75 |

A pergunta sobre fornecedor é a pergunta 20 da limitação L1. Na fase 1, o documento certo ficava na posição 9 e a resposta era "não encontrei". O reranker o põe na posição 1.

## Erro do juiz

Na pergunta sobre as hipóteses de tratamento de dados, as duas fases dão a mesma resposta, com a mesma citação (`lgpd-004.md`), que contém o artigo da lei. Na fase 3, o contexto até fica mais preciso (context precision de 0,33 para 1,00). O juiz deu faithfulness 1,0 na fase 1 e 0,0 na fase 3. A nota 0,0 é um erro do juiz, não do sistema. Com 20 perguntas, um erro desses muda a média em 0,05.

## Tempo e custo

- Cada pergunta levou cerca de 55 s, com 4 perguntas ao mesmo tempo. Quase todo o tempo é o juiz, que faz de 4 a 10 chamadas por pergunta.
- Com o raciocínio do juiz ligado, cada chamada de faithfulness gastou de 3.692 a 4.651 tokens de saída. Com o raciocínio desligado, gastou de 500 a 846, com a mesma nota. O raciocínio ligado também cortou a saída de 3 respostas longas (`IncompleteOutputException`). O padrão do `vlade-rag eval answers` é o raciocínio desligado.
- O custo exato da medida não foi registrado. As execuções desta pasta e a do `legal-ptbr-v2` sem reranker terminaram antes de a chave chegar a US$ 5,00.

## Experimentos no Arize Phoenix

Os três relatórios completos foram publicados no Phoenix local com `vlade-rag eval publish` (ADR-0026). Os traces da medida estão no projeto `vlade-rag-avaliacao`.

| Dataset do Phoenix | Experimento |
|---|---|
| `legal-ptbr` | `fase 1: dense+lexical, sem reranker` |
| `legal-ptbr` | `fase 3: dense+lexical + mongodb/rerank-2.5` |
| `legal-ptbr-v2` | `fase 1: dense+lexical, sem reranker` |

## Limites da medida

- **20 perguntas são poucas para a faithfulness.** Uma pergunta muda a média em 0,05.
- **O juiz erra.** Um erro do juiz apareceu nesta medida. Ninguém conferiu as outras notas à mão.
- **O `legal-ptbr-v2` está incompleto.** Falta a fase 3 das respostas.
- **Só uma execução de cada configuração.** O juiz e o gerador não são determinísticos.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `<dataset>.recuperacao.fase1.json`, `.fase3.json` | `vlade-rag eval run`: Recall@K, Precision@K, MRR e NDCG por pergunta |
| `<dataset>.respostas.fase1.json`, `.fase3.json` | `vlade-rag eval answers`: as quatro métricas do RAGAS, a resposta, as citações e o contexto de cada pergunta |

## Como repetir

Use uma chave de administrador (`VLADE_API_KEY`), a chave do OpenRouter e o extra `eval`:

```bash
vlade-rag eval run legal-ptbr --dataset evals/datasets/legal-ptbr/questions.jsonl \
  --output legal-ptbr.recuperacao.fase1.json
vlade-rag eval answers legal-ptbr --dataset evals/datasets/legal-ptbr/questions.jsonl \
  --judge-model deepseek/deepseek-v4.1-flash --output legal-ptbr.respostas.fase1.json
# Fase 3: as mesmas linhas com --rerank-model mongodb/rerank-2.5
vlade-rag eval publish legal-ptbr.respostas.fase1.json --dataset-name legal-ptbr
```
