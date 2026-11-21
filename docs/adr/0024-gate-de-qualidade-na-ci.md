# ADR-0024: Gate de qualidade na CI

- Status: Aceito
- Data: 2026-11-21

## Contexto

O RF-73 diz: a CI deve falhar se uma métrica de recuperação cai mais que o limite configurado. As métricas de recuperação (RF-70) já existem no comando `vlade-rag eval run`, mas esse comando avalia uma base que já existe e usa os provedores da base. A CI não tem chave de provedor e não deve gastar créditos a cada push. A chave do OpenRouter tem limite de gasto (ver o benchmark da tarefa 3.10).

## Decisão

1. **Comando.** `vlade-rag eval gate` lê `evals/gate/gate.json`, cria um tenant e uma base descartável por dataset, ingere os documentos do dataset e roda a avaliação de recuperação de cada execução listada. Depois, compara as métricas com `evals/gate/baseline.json`.
2. **Sem provedor.** As bases usam embeddings `hashing` e o backend em memória. O gate não chama a rede e dá os mesmos números a cada execução com o mesmo código.
3. **Limite.** O campo `max_drop` (padrão 0,02) é a maior queda absoluta permitida para cada métrica listada em `metrics`. Uma métrica sem linha de base também faz o gate falhar.
4. **Linha de base.** `vlade-rag eval gate --update-baseline` grava as métricas medidas. Uma mudança que melhora ou piora uma métrica de propósito atualiza a linha de base no mesmo pull request. O revisor confere a diferença do arquivo.
5. **Execuções iniciais.** O `gate.json` tem quatro execuções: `legal-ptbr` e `legal-ptbr-v2` com `dense` e `lexical`, `legal-ptbr-v2` só com `lexical`, e `legal-ptbr-v2` com erros de digitação e o retriever `fuzzy`. As métricas são Recall@1, Recall@10, MRR e NDCG@10.
6. **CI.** O job `Quality gate (RF-73)` instala só o extra `cli` e roda o gate. Ele leva cerca de 1 minuto.

## Alternativas avaliadas

- **Gate com o provedor real:** mede a qualidade que o usuário vê, mas gasta créditos a cada push e falha quando o provedor falha. Recusado para a CI. O flow `evaluate_nightly` (tarefa 4.1) pode rodar com o provedor real.
- **Gate com o PostgreSQL:** testa os adapters `tsvector` e `pg_trgm`. Exige o serviço no job e é mais lento. Os testes de integração já cobrem esses adapters. Fica para depois, se um erro de adapter passar pelo gate.
- **Limite relativo (percentual):** uma métrica baixa teria um limite absoluto muito pequeno. O limite absoluto é mais simples de ler.

## Consequências

- O gate detecta regressões de chunking, de fusão, do índice lexical em memória e do retriever fuzzy em memória. Ele não mede a qualidade real: os embeddings `hashing` não têm semântica, e a busca híbrida fica abaixo da busca lexical nessas bases.
- O backend em memória usa um índice BM25 próprio. Uma regressão só do `tsvector` ou do `pg_search` não aparece no gate.
- A linha de base foi medida sem o motor Rust. Os testes de propriedade garantem que o motor Rust e a reserva em Python dão o mesmo resultado. Se eles divergirem, o gate pode falhar só com o motor Rust.
- A limitação L9 fica em parte resolvida: a avaliação roda na CI, mas ainda não roda pela API.
