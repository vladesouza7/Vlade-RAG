# Comparação pgvector e Qdrant

Medida da tarefa 5.1 (ADR-0004). O pgvector é o padrão e a referência. O Qdrant é opcional, no extra `qdrant`.

## Método

`tests/integration/test_qdrant_equivalence.py` executa os passos abaixo com PostgreSQL:

1. Cria uma base com embeddings `hashing` de 64 dimensões.
2. Ingere dez documentos com o índice pgvector.
3. Copia os vetores do espaço para um cliente Qdrant em processo.
4. Roda `RetrievalEvaluator` com seis perguntas e `k = 10` nos dois índices, sem cache.

O teste usa o mesmo espaço, os mesmos vetores e a mesma configuração de recuperação nos dois casos. A diferença máxima permitida é de dois pontos percentuais de Recall@10.

## Resultado (2026-11-23)

| Índice | Recall@10 |
|---|---|
| pgvector | 1,000 |
| Qdrant | 1,000 |
| Diferença | 0,000 |

Os dois índices devolveram o documento relevante nas dez primeiras posições de todas as perguntas. O dataset sintético é pequeno e usa correspondência de palavras, então não separa configurações. O resultado confirma a equivalência da implementação, não a superioridade de um índice.
