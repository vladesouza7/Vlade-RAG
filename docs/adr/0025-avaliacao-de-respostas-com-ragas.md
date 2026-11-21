# ADR-0025: Avaliação de respostas com RAGAS

- Status: Aceito
- Data: 2026-11-21

## Contexto

O RF-71 pede quatro métricas de resposta com RAGAS: faithfulness, answer relevancy, context precision e context recall. O critério de aceite da fase 3 pede um relatório que compare a configuração da fase 1 com a da fase 3 no mesmo dataset, com Recall@10 e faithfulness. As métricas de recuperação (RF-70) já existem e não usam LLM. As métricas do RAGAS usam um LLM juiz e um modelo de embeddings.

O RAGAS 0.4 tem uma API nova (`ragas.metrics.collections`). Cada métrica recebe as entradas de uma amostra e devolve a pontuação. O RAGAS usa a licença Apache-2.0, mas traz dependências pesadas: pandas, pyarrow, scipy e langchain-community.

## Decisão

1. **Avaliador.** O `AnswerEvaluator` (`vlade_rag.evaluation.answers`) roda cada pergunta pelo fluxo de consulta da base, com o motor configurado (ADR-0023). Ele pontua a resposta e o contexto que o usuário recebe. As opções `--retrievers` e `--rerank-model` mudam a configuração só nesta execução.
2. **Pontuador.** O `RagasScorer` (`vlade_rag.evaluation.ragas`) calcula as quatro métricas do RF-71 com `Faithfulness`, `AnswerRelevancy`, `ContextPrecisionWithReference` e `ContextRecall`. Ele chama o juiz e os embeddings por uma API compatível com a da OpenAI. O padrão é o OpenRouter, com a chave da configuração do servidor.
3. **Métrica sem valor.** Uma métrica que falha ou devolve NaN fica fora da média daquela pergunta. O relatório conta as perguntas pontuadas por métrica e lista os erros do juiz. Uma recusa ("não encontrei") sem contexto não tem faithfulness. Context precision e context recall exigem a resposta esperada.
4. **Limite de saída do juiz.** O padrão é 8192 tokens por chamada (`--judge-max-tokens`). O padrão do RAGAS (1024) corta a lista de afirmações do faithfulness em respostas longas.
5. **Comando.** `vlade-rag eval answers <base> --dataset <arquivo> --judge-model <modelo>`. O relatório JSON registra a configuração da base, o juiz, os embeddings e a versão do RAGAS (RF-72), e o detalhe de cada pergunta.
6. **Extra.** O RAGAS fica no extra `eval`, fora do extra `server`. A verificação de licenças da CI cobre o extra.
7. **Testes.** Os testes usam um pontuador falso e métricas falsas. Nenhum teste chama o juiz.

## Alternativas avaliadas

- **Avaliar só a resposta final (`AnswerQuery.execute`):** a resposta não traz o texto do contexto, e o faithfulness precisa dele. Recusado.
- **API antiga do RAGAS (`evaluate` com `EvaluationDataset`):** mistura a execução e a pontuação e usa a camada do LangChain. A API nova é mais simples de testar. Recusado.
- **Juiz igual ao gerador:** o modelo avaliaria a própria resposta. O juiz padrão da medida é de outra família.

## Consequências

- Cada pergunta custa uma geração na base e de 4 a 10 chamadas ao juiz. O relatório da medida em `evals/reports/fase3-ragas/` mostra o tempo e o custo de uma execução.
- O juiz às vezes não termina a saída estruturada (`IncompleteOutputException`), mesmo com 8192 tokens. A pergunta fica sem faithfulness, e o relatório conta o erro.
- O resultado depende do juiz. Comparações valem só entre execuções com o mesmo juiz e os mesmos embeddings.
