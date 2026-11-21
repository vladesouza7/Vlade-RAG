# ADR-0026: Arize Phoenix no lugar do Langfuse

- Status: Aceito
- Data: 2026-11-21
- Substitui o item 2 e o item 5 do ADR-0015
- Decisão no VLADE-RAG.md: D10

## Contexto

O item 2 do ADR-0015 escolhe o Langfuse para os traces de IA, os prompts versionados e os experimentos de avaliação. O Langfuse auto-hospedado (versão 3) precisa de ClickHouse, Redis, PostgreSQL e armazenamento S3. O notebook de desenvolvimento tem 8 GB de RAM e não comporta esses serviços junto com o resto. O mantenedor decidiu deixar o Langfuse de fora por enquanto e usar o Arize Phoenix.

O teste de 2026-11-21 com a imagem `arizephoenix/phoenix:version-22.0.0` deu este resultado:

- O Phoenix é um container só, com SQLite. Ele usou cerca de 475 MB de memória sem carga.
- Ele recebe traces OTLP por HTTP em `/v1/traces`, na porta 6006, a mesma da interface. Ele não recebe métricas (`/v1/metrics` devolve 405).
- A versão 22 liga a autenticação por padrão.
- A API REST cria datasets, experimentos, runs e avaliações.
- O servidor usa a Elastic License 2.0. Ela não é de código aberto pela definição da OSI e proíbe oferecer o Phoenix como serviço gerenciado. Os clientes (`arize-phoenix-otel`, `arize-phoenix-client`) e as convenções OpenInference usam Apache-2.0.

O teste também achou um erro anterior: o `build_runtime` recebia o tracer e não o passava aos casos de uso. Só o span HTTP da API chegava ao coletor.

## Decisão

1. **Serviço.** O Compose tem o serviço `phoenix` (versão fixa 22.0.0) no perfil `phoenix`: `docker compose --profile dev --profile phoenix up`. A porta 6006 escuta só em `127.0.0.1`, e a autenticação fica desligada (`PHOENIX_ENABLE_AUTH=false`). O Phoenix recusa um `PHOENIX_SECRET` vazio, então o Compose não passa essa variável. Para ligar a autenticação, o operador usa um arquivo `docker-compose.override.yml` com `PHOENIX_ENABLE_AUTH=true` e `PHOENIX_SECRET`. Depois ele define a chave `PHOENIX_API_KEY` para a publicação e `OTEL_EXPORTER_OTLP_HEADERS` para os traces.
2. **Licença.** O Phoenix roda como serviço separado, sem modificação, e não entra no pacote Python (seção 16.1 do `VLADE-RAG.md`, item 4). O Vlade-RAG não depende de nenhum pacote do Phoenix: ele envia OTLP e chama a API REST com a biblioteca padrão.
3. **Traces.** O código continua com OpenTelemetry. Os spans de IA ganham os atributos das convenções OpenInference (`openinference.span.kind`, `llm.model_name`, `llm.token_count.*`, `retrieval.documents.*`, `reranker.*`), que o Phoenix lê. Os casos de uso `AnswerQuery.execute` e `Search.execute` criam um span raiz (`query` e `search`), para cada consulta da CLI e do MCP virar um trace só. O texto da pergunta, da resposta e dos chunks entra nos spans só com `VLADE_LIMITS__STORE_QUERY_TEXT=true`, a mesma regra do log de consultas.
4. **Configuração.** `VLADE_OTEL__METRICS=false` desliga o envio de métricas, porque o Phoenix não as recebe. `VLADE_OTEL__PROJECT` define o projeto dos traces no Phoenix (atributo `openinference.project.name`). A CLI também liga a telemetria e envia os spans antes de terminar.
5. **Experimentos.** `vlade-rag eval publish <relatório>` publica um relatório do `eval answers` no Phoenix: o dataset (perguntas e respostas esperadas), o experimento (a configuração), um run por pergunta e uma avaliação por métrica.
6. **Prompts versionados.** O Phoenix tem um registro de prompts, mas esta decisão não o usa. Os prompts continuam no `BuiltinPromptRegistry`, com nome e versão em cada resposta.
7. **Volta do Langfuse.** Quando houver uma máquina com memória para o Langfuse, um ADR novo pode trazê-lo de volta. Os traces continuam em OpenTelemetry, então a troca não muda os casos de uso.

## Alternativas avaliadas

- **Langfuse auto-hospedado:** não cabe no notebook. Recusado por enquanto.
- **Langfuse Cloud:** envia os traces e os dados de avaliação a um terceiro. O mantenedor preferiu um serviço local.
- **Só a stack LGTM (Tempo):** guarda os traces, mas não mostra os spans de IA nem os experimentos de avaliação.
- **Pacote `arize-phoenix-otel` ou `openinference-instrumentation`:** acrescentam dependências para o que o código já faz com atributos simples. Recusado.

## Consequências

- O perfil `phoenix` acrescenta cerca de 500 MB de memória.
- A interface do Phoenix fica em `http://127.0.0.1:6006`, sem senha. Quem expõe a porta fora da máquina deve ligar a autenticação.
- Os prompts versionados em serviço externo ficam sem implementação (limitação L22).
- A correção do `build_runtime` faz os casos de uso enviarem spans também para a stack LGTM, quando ela existir (fase 4).
