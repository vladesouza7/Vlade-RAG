# ADR-0030: Cache semântico de consultas

- Status: Aceito
- Data: 2026-11-23

## Contexto

O cache da seção 11.6 da arquitetura guarda o resultado de uma busca pela chave exata da pergunta. Duas perguntas com o mesmo sentido, mas com palavras diferentes, não compartilham a entrada. A tarefa 5.4 pede um cache semântico.

O projeto já tem um port `Cache` com adapters em memória e no Valkey (ADR-0007). Não há dependência vetorial no núcleo, e a política da ADR-0001 desaconselha acrescentar uma só para medir similaridade entre duas perguntas curtas.

## Decisão

1. **Camada.** `SemanticCache` fica em `core/application` e usa somente o port `Cache`. Ele guarda o vetor da pergunta e os identificadores do resultado, com o mesmo formato do cache exato.
2. **Chave.** A chave é `semsearch:{kb_id}:{epoch}`. A época da base muda ao publicar, apagar ou reindexar. Uma entrada antiga nunca é lida depois disso, e não é preciso varrer o cache.
3. **Similaridade.** A busca compara o vetor novo com os vetores guardados por cosine. Se a maior similaridade atingir o limiar, o resultado antigo volta. O cálculo usa apenas a biblioteca padrão e arredonda os vetores a quatro casas decimais antes de gravar.
4. **Escopo.** O cache semântico funciona só para busca densa, sem filtros de metadados e sem transformação de consulta. O caso de uso `Search` precisa do vetor da pergunta, que já passa pelo cache de embeddings da seção 11.6.
5. **Configuração.** O recurso começa desligado. `VLADE_CACHE__SEMANTIC__ENABLED` liga. `THRESHOLD` define a similaridade mínima, `MAX_ENTRIES` limita o número de perguntas guardadas por base e `TTL_SECONDS` define a validade da entrada.
6. **Falhas.** Se o cache falhar, a leitura devolve uma ausência e a busca segue normalmente. O comportamento fail-open do adapter Valkey continua válido (limitação L4).
7. **Testes.** `tests/unit/test_semantic_cache.py` cobre limiar, época, isolamento entre tenants e limite de entradas. `tests/integration/test_search_cache.py` confirma que uma pergunta com outras palavras, mas com o mesmo sentido, não chama a fusão de novo.

## Alternativas avaliadas

- **Busca vetorial no Valkey:** exigiria um módulo de busca vetorial no servidor e uma dependência nova no cliente. Recusado para um conjunto pequeno de perguntas por base.
- **Usar o índice HNSW do pgvector:** daria similaridade precisa, mas acrescentaria uma consulta ao banco antes da busca e outra dependência do cache em relação ao banco. Recusado.
- **Substituir o cache exato:** mudaria o comportamento padrão e poderia devolver resultado de uma pergunta diferente. O cache semântico ficou opt-in e complementar.
- **Guardar o texto da pergunta:** economizaria o vetor, mas exigiria embeddar cada texto guardado na leitura e exporia mais dado pessoal no cache.

## Consequências

- Cada acerto do cache semântico evita a transformação, a recuperação, a fusão e o reranking.
- O custo é um vetor por pergunta guardada. Com 128 entradas e 1024 dimensões, o valor JSON fica na faixa de poucas centenas de quilobytes por base.
- Um limiar baixo pode devolver resultado de uma pergunta diferente. O padrão de 0,98 é conservador. Operadores podem ajustar com medida própria.
- A limitação L23 continua restrita ao download de URI. Ela não se aplica a este cache.
