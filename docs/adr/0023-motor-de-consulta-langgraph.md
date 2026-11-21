# ADR-0023: Motor de consulta LangGraph

- Status: Aceito
- Data: 2026-11-21
- Complementa o item 2 do ADR-0011

## Contexto

O item 2 do ADR-0011 define duas implementações do fluxo de consulta: um pipeline linear em Python (padrão) e um grafo LangGraph (opcional). A seção 12.1 do `ARCHITECTURE.md` define as duas arestas condicionais do grafo e exige um teste de igualdade entre os dois motores. Ela não define onde fica a configuração, como o grafo reaproveita os passos do pipeline nem o que acontece com o streaming quando o grafo repete uma tentativa.

Antes desta decisão, o caso de uso `AnswerQuery` fazia toda a sequência em um método só. O núcleo não pode depender do LangGraph (ADR-0011, alternativa "LangGraph obrigatório").

## Decisão

1. **Passos.** O `AnswerQuery` expõe os passos do fluxo: `prepare`, `retrieve`, `assemble`, `generate` e `validate`. Um motor (`AnswerEngine`) chama os passos e devolve o texto em streaming e um `Draft` final. O `AnswerQuery` monta a resposta e grava o `QueryLog` depois do motor. Os dois motores usam os mesmos passos e os mesmos spans.
2. **Motores.** O `PipelineEngine` fica no núcleo e roda cada passo uma vez. O `LangGraphEngine` fica em `vlade_rag.orchestration.langgraph`, no extra `langgraph` (LangGraph 1.2, licença MIT). O runtime registra os motores instalados em `Dependencies.answer_engines`. Sem registro, o pipeline continua a rodar.
3. **Configuração por base.** A seção `orchestration` da configuração da base tem quatro campos:
   - `engine`: `pipeline` (padrão) ou `langgraph`. Se a base pede `langgraph` e o extra não está instalado, a consulta devolve `invalid_argument`.
   - `rewrite_below_score`: se o melhor resultado tem pontuação abaixo desse valor e `retrieval.query_transform` é `none`, o grafo reescreve a consulta uma vez com o transformador `rewrite` (ADR-0019) e busca de novo. O padrão `null` desliga a aresta. A pontuação é a que o `Search` devolve: RRF, ou a do reranker quando ele está ligado.
   - `max_attempts`: número de buscas quando a resposta não tem fundamento (`grounded = false`). O padrão `1` desliga a aresta. O máximo é 3.
   - `retry_top_k_factor`: cada tentativa nova multiplica o `top_k` por esse fator, até o limite do servidor (`max_top_k`). Sem espaço para crescer, o grafo para.
4. **Consulta reescrita.** A reescrita muda só a consulta dos retrievers. O prompt sempre usa a pergunta original. Se a reescrita não devolve um texto novo, o grafo segue sem buscar de novo.
5. **Streaming.** O grafo envia o texto de cada geração assim que ele chega. Se uma tentativa nova acontece, o cliente já recebeu o texto da tentativa anterior. Nesse caso, o evento final tem `replaced = true` e traz o texto final, como já acontece quando a validação muda o texto (seção 11.5).
6. **Igualdade.** Com `rewrite_below_score = null` e `max_attempts = 1`, os dois motores devolvem a mesma resposta e os mesmos eventos de streaming. O teste `tests/integration/test_query_engines.py` confere isso com o backend em memória e com o PostgreSQL.

## Alternativas avaliadas

- **Configuração no servidor (`VLADE_*`), não na base:** um servidor teria um motor só para todas as bases. A configuração por base permite testar o grafo em uma base sem mudar as outras. Recusado.
- **Grafo que reimplementa os passos:** dois códigos para a mesma sequência divergem com o tempo, e o teste de igualdade perde o sentido. Recusado.
- **Desligar o streaming no motor LangGraph:** o cliente esperaria a resposta inteira. Recusado. O campo `replaced` já existe para o caso em que o texto final muda.
- **Pôr o extra `langgraph` no extra `server`:** a imagem padrão ficaria maior para um motor opcional. O extra fica separado. A CI instala o extra e verifica a licença dele.

## Consequências

- O LangGraph é opcional. O padrão continua `pipeline`, e nenhuma base muda de comportamento.
- Uma tentativa nova custa uma busca e uma chamada ao LLM a mais. Uma reescrita custa uma chamada ao LLM e uma busca a mais.
- O limite `rewrite_below_score` depende da escala da pontuação: a do RRF (cerca de 0,01 a 0,03) é diferente da do reranker (0 a 1). Quem muda o reranker deve rever o limite.
- Ninguém mediu o ganho de qualidade das duas arestas. A medida precisa de um LLM real e de um dataset com perguntas sem fundamento.
