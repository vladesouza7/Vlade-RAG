# Gate de qualidade (RF-73)

O gate compara as métricas de recuperação com a linha de base desta pasta. Ele falha se uma métrica cai mais que `max_drop`. A decisão está no ADR-0024.

| Arquivo | Conteúdo |
|---|---|
| `gate.json` | O limite, as métricas, a configuração das bases e as execuções |
| `baseline.json` | As métricas de referência de cada execução |

## Rodar

O gate usa o backend em memória e embeddings `hashing`. Ele não chama nenhum provedor.

```bash
VLADE_STORAGE__BACKEND=memory VLADE_OBJECT_STORAGE__BACKEND=memory uv run vlade-rag eval gate
```

O comando mostra cada métrica, a linha de base e a variação. O código de saída é 1 quando o gate falha.

## Atualizar a linha de base

Atualize a linha de base só quando uma mudança altera uma métrica de propósito:

```bash
VLADE_STORAGE__BACKEND=memory VLADE_OBJECT_STORAGE__BACKEND=memory uv run vlade-rag eval gate --update-baseline
```

Faça o commit do `baseline.json` no mesmo pull request da mudança. Explique a variação na descrição do pull request.

## O que o gate não mede

- A qualidade real. Os embeddings `hashing` não têm semântica, e a busca híbrida fica abaixo da busca lexical nestas bases.
- Os índices do PostgreSQL (`tsvector`, `pg_trgm` e `pg_search`). O backend em memória tem índices próprios.
- O reranker e as transformações de consulta com LLM.
