# Vlade-RAG — Especificação do servidor MCP

> Versão do contrato: 1.2.0 — 2026-11-25. A versão 1.1.0 acrescentou `vlade_search_graph`. A versão 1.2.0 acrescenta as ferramentas de wiki (seções 5.12 a 5.15).
> Fonte: seção 12 do [`VLADE-RAG.md`](../VLADE-RAG.md). Arquitetura: [`ARCHITECTURE.md`](ARCHITECTURE.md). Decisão: [ADR-0013](adr/0013-mcp-qualquer-cliente.md).

---

## 1. Objetivo

O servidor `vlade-rag-mcp` expõe as bases de conhecimento do Vlade-RAG para qualquer cliente MCP. Exemplos de clientes: Claude Code, Hermes Agent, agentes LangGraph com `langchain-mcp-adapters`, IDEs.

O servidor segue só a especificação do Model Context Protocol. O servidor não tem código específico para um cliente.

## 2. Implementação

| Item | Valor |
|---|---|
| Módulo | `vlade_rag.mcp` |
| SDK | SDK oficial `mcp` para Python |
| Comando | `vlade-rag mcp serve --transport stdio` ou `vlade-rag mcp serve --transport http --host 0.0.0.0 --port 8765` |
| Transportes | `stdio` e Streamable HTTP. O servidor não suporta o transporte SSE antigo |
| Caminho HTTP | `/mcp` |
| Camada chamada | Só casos de uso de `vlade_rag.core.application` |

## 3. Autenticação e tenant

### 3.1. Transporte `stdio`

O servidor lê a chave de API da variável de ambiente `VLADE_API_KEY` na inicialização. Se a chave não existe ou é inválida, o servidor encerra com código 1 e grava o motivo em `stderr`.

### 3.2. Transporte HTTP

1. O cliente envia `Authorization: Bearer <credencial>` em cada requisição. A credencial é a chave de API ou um token de acesso OIDC.
2. Se a credencial não existe ou é inválida, o servidor responde HTTP 401 com `WWW-Authenticate: Bearer`.
3. A versão 1 usa chaves de API. A fase 5 acrescenta OAuth 2.1 (ADR-0031), com verificação do token contra o emissor e o JWKS configurados.
4. As chaves de API continuam válidas com OIDC ligado. O servidor tenta a chave primeiro e verifica o token quando a credencial tem forma de JWT.

### 3.3. Tenant

O servidor deriva o tenant e os papéis da credencial verificada. Nenhuma ferramenta aceita `tenant_id` como parâmetro. O `slug` identifica a base dentro do tenant da credencial. Os claims `tenant` e `roles` do token são configuráveis.

## 4. Política de ferramentas

| Regra | Descrição |
|---|---|
| Leitura por padrão | O servidor lista só as ferramentas de leitura, a menos que `tenants.settings.mcp.write_tools_enabled` seja `true` |
| Papel por ferramenta | O servidor verifica o papel mínimo de cada ferramenta em cada chamada. O caso de uso verifica de novo |
| Lista filtrada | `tools/list` devolve só as ferramentas que o papel da chave pode chamar |
| Confirmação | Uma ferramenta destrutiva sem `confirm: true` devolve uma prévia e não executa |
| Auditoria | Cada chamada grava um `AuditEvent` com `interface = mcp` |
| Limite de requisições | O mesmo token bucket da API, por chave (seção 8) |
| Saída estruturada | Cada ferramenta declara `outputSchema` e devolve `structuredContent`. O servidor também devolve o mesmo JSON como bloco de texto, para clientes sem suporte a saída estruturada |

## 5. Ferramentas

### 5.1. Resumo

| Ferramenta | Tipo | Papel mínimo | `readOnlyHint` | `destructiveHint` | `idempotentHint` |
|---|---|---|---|---|---|
| `vlade_list_knowledge_bases` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_search` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_query` | Leitura | `reader` | `true` | `false` | `false` |
| `vlade_get_document` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_get_ingestion_status` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_search_graph` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_wiki_read` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_wiki_lint` | Leitura | `reader` | `true` | `false` | `true` |
| `vlade_ingest_document` | Escrita | `writer` | `false` | `false` | `false` |
| `vlade_delete_document` | Escrita destrutiva | `admin` | `false` | `true` | `true` |
| `vlade_reindex_knowledge_base` | Escrita destrutiva | `admin` | `false` | `true` | `false` |
| `vlade_evaluate` | Operação | `admin` | `false` | `false` | `false` |
| `vlade_wiki_write` | Escrita | `writer` | `false` | `false` | `false` |
| `vlade_wiki_synthesize` | Escrita | `writer` | `false` | `false` | `false` |

Todas as ferramentas têm `openWorldHint: false`.

O servidor lista e aceita `vlade_search_graph` só quando tem um grafo de conhecimento configurado (`VLADE_GRAPH__DATABASE_URL`, ADR-0032). O servidor lista e aceita as quatro ferramentas de wiki só quando tem um `WikiStore` (`VLADE_WIKI__ENABLED=true`, ADR-0033).

### 5.2. `vlade_list_knowledge_bases`

Descrição para o modelo:

> Lista as bases de conhecimento que a sua chave pode ler. Use esta ferramenta antes de `vlade_search` ou `vlade_query` se você não sabe o `slug` da base.

Entrada:

```json
{ "type": "object", "properties": {}, "additionalProperties": false }
```

Saída:

```json
{
  "type": "object",
  "required": ["knowledge_bases"],
  "properties": {
    "knowledge_bases": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["slug", "name", "language", "document_count", "updated_at"],
        "properties": {
          "slug": { "type": "string" },
          "name": { "type": "string" },
          "language": { "type": "string" },
          "document_count": { "type": "integer" },
          "updated_at": { "type": "string", "format": "date-time" }
        }
      }
    }
  }
}
```

### 5.3. `vlade_search`

Descrição para o modelo:

> Busca trechos de documentos em uma base de conhecimento. Devolve os trechos com pontuação e a origem de cada trecho. Use esta ferramenta quando você quer ler as fontes e escrever a resposta você mesmo. Para receber uma resposta pronta com citações, use `vlade_query`.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "query"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string", "description": "Slug da base." },
    "query": { "type": "string", "minLength": 1, "maxLength": 4000 },
    "top_k": { "type": "integer", "minimum": 1, "maximum": 50, "default": 8 },
    "filters": {
      "type": "object",
      "description": "Filtro por metadados do documento. Formato: {\"campo\": valor} para igualdade, ou {\"campo\": {\"in\": [valores]}}.",
      "additionalProperties": true
    },
    "rerank": { "type": "boolean", "description": "Sem valor: usa a configuração da base." }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["results", "trace_id"],
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rank", "score", "chunk_id", "document_id", "document_title", "text"],
        "properties": {
          "rank": { "type": "integer" },
          "score": { "type": "number" },
          "chunk_id": { "type": "string", "format": "uuid" },
          "document_id": { "type": "string", "format": "uuid" },
          "document_title": { "type": "string" },
          "text": { "type": "string" },
          "page": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
          "section": { "anyOf": [{ "type": "string" }, { "type": "null" }] },
          "resource_uri": { "type": "string", "description": "URI do resource do documento." }
        }
      }
    },
    "trace_id": { "anyOf": [{ "type": "string" }, { "type": "null" }] }
  }
}
```

### 5.4. `vlade_query`

Descrição para o modelo:

> Faz uma pergunta a uma base de conhecimento e devolve uma resposta gerada só a partir das fontes, com citações no formato [n]. Se `grounded` é false, as fontes não têm a resposta. Nesse caso, não complete a resposta com conhecimento próprio sem avisar o usuário.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "question"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string" },
    "question": { "type": "string", "minLength": 1, "maxLength": 4000 },
    "top_k": { "type": "integer", "minimum": 1, "maximum": 50 },
    "filters": { "type": "object", "additionalProperties": true },
    "language": { "type": "string", "enum": ["pt-BR", "en"] }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["answer", "grounded", "citations", "trace_id"],
  "properties": {
    "answer": { "type": "string" },
    "grounded": { "type": "boolean" },
    "citations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["index", "document_id", "chunk_id", "document_title"],
        "properties": {
          "index": { "type": "integer" },
          "document_id": { "type": "string", "format": "uuid" },
          "chunk_id": { "type": "string", "format": "uuid" },
          "document_title": { "type": "string" },
          "page": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
          "resource_uri": { "type": "string" }
        }
      }
    },
    "model": { "type": "string" },
    "prompt_version": { "type": "string" },
    "usage": {
      "type": "object",
      "properties": {
        "input_tokens": { "type": "integer" },
        "output_tokens": { "type": "integer" }
      }
    },
    "trace_id": { "anyOf": [{ "type": "string" }, { "type": "null" }] }
  }
}
```

A versão 1 não faz streaming pelo MCP. Durante a geração, o servidor envia notificações de progresso se o cliente informa um `progressToken`.

### 5.5. `vlade_get_document`

Descrição para o modelo:

> Lê os metadados de um documento e, se você pedir, o texto do documento. O texto pode vir cortado. Nesse caso, `truncated` é true.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "document_id"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string" },
    "document_id": { "type": "string", "format": "uuid" },
    "include_text": { "type": "boolean", "default": false },
    "max_chars": { "type": "integer", "minimum": 1000, "maximum": 100000, "default": 20000 }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["document"],
  "properties": {
    "document": {
      "type": "object",
      "required": ["id", "title", "source_type", "mime_type", "metadata"],
      "properties": {
        "id": { "type": "string", "format": "uuid" },
        "title": { "type": "string" },
        "source_type": { "type": "string" },
        "source_uri": { "anyOf": [{ "type": "string" }, { "type": "null" }] },
        "mime_type": { "type": "string" },
        "version": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
        "metadata": { "type": "object", "additionalProperties": true },
        "created_at": { "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }] },
        "updated_at": { "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }] },
        "text": { "type": "string" },
        "truncated": { "type": "boolean" }
      }
    }
  }
}
```

`text` e `truncated` aparecem só se `include_text` é `true`.

### 5.6. `vlade_get_ingestion_status`

Descrição para o modelo:

> Informa o estado de um job de ingestão, de reindexação ou de avaliação. Os estados finais são succeeded, failed e cancelled.

Entrada:

```json
{
  "type": "object",
  "required": ["job_id"],
  "additionalProperties": false,
  "properties": { "job_id": { "type": "string", "format": "uuid" } }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["job"],
  "properties": {
    "job": {
      "type": "object",
      "required": ["id", "kind", "status", "steps"],
      "properties": {
        "id": { "type": "string", "format": "uuid" },
        "kind": { "type": "string" },
        "status": { "type": "string" },
        "steps": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "status", "attempt"],
            "properties": {
              "name": { "type": "string" },
              "status": { "type": "string" },
              "attempt": { "type": "integer" },
              "error": { "anyOf": [{ "type": "object", "additionalProperties": true }, { "type": "null" }] }
            }
          }
        },
        "result": { "anyOf": [{ "type": "object", "additionalProperties": true }, { "type": "null" }] },
        "error": { "anyOf": [{ "type": "object", "additionalProperties": true }, { "type": "null" }] },
        "created_at": { "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }] },
        "started_at": { "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }] },
        "finished_at": { "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }] }
      }
    }
  }
}
```

### 5.7. `vlade_ingest_document`

Descrição para o modelo:

> Envia um documento para uma base de conhecimento. A ingestão é assíncrona. A ferramenta devolve um job_id. Use `vlade_get_ingestion_status` para acompanhar o job. Envie o texto em `content_text` ou um endereço em `source_uri`. Não envie os dois.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "filename"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string" },
    "filename": { "type": "string", "maxLength": 255 },
    "content_text": { "type": "string", "maxLength": 1000000 },
    "source_uri": { "type": "string", "format": "uri" },
    "title": { "type": "string" },
    "external_id": { "type": "string", "maxLength": 255 },
    "metadata": { "type": "object", "additionalProperties": true }
  },
  "oneOf": [
    { "required": ["content_text"] },
    { "required": ["source_uri"] }
  ]
}
```

Regras:

1. `content_text` aceita só texto: texto puro, Markdown ou HTML. O tipo vem da extensão de `filename`.
2. `source_uri` aceita `s3://` no bucket do tenant e `https://`. O download por `https://` segue a lista de domínios permitidos (seção 15 do `ARCHITECTURE.md`). Se a lista está vazia, o servidor recusa `https://`.
3. Se `external_id` já existe na base, a ingestão cria uma versão nova do documento existente.

Saída:

```json
{
  "type": "object",
  "required": ["job_id", "document_id", "status"],
  "properties": {
    "job_id": { "type": "string", "format": "uuid" },
    "document_id": { "type": "string", "format": "uuid" },
    "status": { "type": "string", "enum": ["pending", "succeeded"] }
  }
}
```

`pending` é o caso normal. `succeeded` aparece quando o conteúdo é igual à versão atual: o job termina sem ingerir de novo.

### 5.8. `vlade_delete_document`

Descrição para o modelo:

> Apaga um documento, todas as versões, os trechos, os vetores e o arquivo original. A exclusão não pode ser desfeita. Primeiro chame a ferramenta sem `confirm` para ver a prévia. Mostre a prévia ao usuário. Chame de novo com `confirm: true` só depois de o usuário aprovar.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "document_id"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string" },
    "document_id": { "type": "string", "format": "uuid" },
    "confirm": { "type": "boolean", "default": false }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["executed", "action"],
  "properties": {
    "executed": { "type": "boolean" },
    "action": { "type": "string", "const": "delete_document" },
    "document_title": { "type": "string" },
    "will_delete": {
      "type": "object",
      "required": ["versions", "chunks", "embeddings", "stored_objects"],
      "properties": {
        "versions": { "type": "integer" },
        "chunks": { "type": "integer" },
        "embeddings": { "type": "integer" },
        "stored_objects": { "type": "integer" }
      }
    },
    "audit_event_id": { "type": "string", "format": "uuid" }
  }
}
```

Sem confirmação, a saída traz `document_title` e `will_delete`, com `executed: false`. Com confirmação, a saída traz `audit_event_id` e `executed: true`.

### 5.9. `vlade_reindex_knowledge_base`

Descrição para o modelo:

> Reindexa uma base de conhecimento. O modo embeddings gera os vetores de novo com o modelo informado. O modo full processa de novo todos os arquivos originais. A reindexação consome tempo e custo de provedor. Primeiro chame a ferramenta sem `confirm` para ver a estimativa. Chame de novo com `confirm: true` só depois de o usuário aprovar.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "mode"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string" },
    "mode": { "type": "string", "enum": ["embeddings", "full"] },
    "embedding_model": { "type": "string", "description": "Só no modo embeddings. Sem valor: usa o modelo da configuração atual." },
    "confirm": { "type": "boolean", "default": false }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["executed", "action"],
  "properties": {
    "executed": { "type": "boolean" },
    "action": { "type": "string", "const": "reindex_knowledge_base" },
    "knowledge_base": { "type": "string" },
    "mode": { "type": "string", "enum": ["embeddings", "full"] },
    "documents": { "type": "integer" },
    "chunks": { "type": "integer" },
    "estimated_embedding_calls": { "type": "integer" },
    "job_id": { "type": "string", "format": "uuid" }
  }
}
```

Sem confirmação, a saída traz `documents`, `chunks` e `estimated_embedding_calls`, com `executed: false`. Com confirmação, a saída traz `job_id` e `executed: true`.

Se já existe uma reindexação em andamento na base, a ferramenta devolve o erro `conflict`.

### 5.10. `vlade_evaluate`

Descrição para o modelo:

> Inicia uma avaliação de qualidade de uma base com um dataset registrado. A avaliação é assíncrona e devolve um job_id.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "dataset"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string" },
    "dataset": { "type": "string", "description": "Nome do dataset registrado." },
    "metrics": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["recall_at_k", "precision_at_k", "mrr", "ndcg"]
      }
    },
    "k": { "type": "integer", "minimum": 1, "maximum": 50 }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["job_id"],
  "properties": { "job_id": { "type": "string", "format": "uuid" } }
}
```

O job grava o relatório no campo `result`. As métricas de resposta com juiz pago (`faithfulness`, `answer_relevancy`, `context_precision` e `context_recall`) continuam só na CLI `vlade-rag eval answers`.

### 5.11. `vlade_search_graph`

Descrição para o modelo:

> Explora o grafo de conhecimento de uma base: entidades, relações entre entidades e os trechos que sustentam essas relações. Use esta ferramenta para perguntas que comparam autores, conceitos ou eventos. A base precisa ter o grafo ligado.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "query"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": { "type": "string", "description": "Slug da base." },
    "query": { "type": "string", "minLength": 1, "maxLength": 4000 },
    "mode": {
      "type": "string",
      "enum": ["local", "global", "hybrid", "mix", "naive"],
      "description": "Sem valor: usa a configuração da base."
    },
    "top_k": { "type": "integer", "minimum": 1, "maximum": 200 }
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["entities", "relations", "chunks", "trace_id"],
  "properties": {
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "type", "description"],
        "properties": {
          "name": { "type": "string" },
          "type": { "type": "string" },
          "description": { "type": "string" }
        }
      }
    },
    "relations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["source", "target", "keywords", "description", "weight"],
        "properties": {
          "source": { "type": "string" },
          "target": { "type": "string" },
          "keywords": { "type": "string" },
          "description": { "type": "string" },
          "weight": { "type": "number" }
        }
      }
    },
    "chunks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rank", "score", "chunk_id", "document_id", "document_title", "text"],
        "properties": {
          "rank": { "type": "integer" },
          "score": { "type": "number" },
          "chunk_id": { "type": "string", "format": "uuid" },
          "document_id": { "type": "string", "format": "uuid" },
          "document_title": { "type": "string" },
          "text": { "type": "string" },
          "page": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
          "section": { "anyOf": [{ "type": "string" }, { "type": "null" }] },
          "resource_uri": { "type": "string", "description": "URI do resource do documento." }
        }
      }
    },
    "trace_id": { "anyOf": [{ "type": "string" }, { "type": "null" }] }
  }
}
```

Regras:

1. Se a base não tem o grafo ligado (`graph.enabled`), a ferramenta devolve o erro `invalid_argument`.
2. Os trechos são só de versões publicadas. Um trecho de uma versão antiga não aparece.
3. As entidades e as relações não têm citação própria. Para citar, use os trechos da lista `chunks`.

### 5.12. `vlade_wiki_read`

> Lê a wiki de uma base. Sem 'path', lista as páginas com título e descrição. Com 'path', devolve o conteúdo OKF da página.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": {"type": "string", "minLength": 1, "maxLength": 63},
    "path": {"type": "string", "minLength": 1, "maxLength": 256}
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["pages"],
  "properties": {
    "pages": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "path": {"type": "string"},
          "type": {"type": "string"},
          "title": {"type": "string"},
          "description": {"type": "string"},
          "content": {"type": "string"}
        }
      }
    }
  }
}
```

Regras: o campo `path` é relativo à raiz do bundle. A ferramenta devolve `[]` quando a wiki não tem páginas.

### 5.13. `vlade_wiki_lint`

> Verifica a wiki de uma base: links quebrados, páginas órfãs, páginas vencidas e arquivos index.md e log.md ausentes.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": {"type": "string", "minLength": 1, "maxLength": 63}
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["pages", "links", "problems"],
  "properties": {
    "pages": {"type": "integer"},
    "links": {"type": "integer"},
    "problems": {"type": "array", "items": {"type": "string"}}
  }
}
```

Regras: o lint não chama LLM. Ele lê o campo `stale_after` e os links Markdown do corpo das páginas.

### 5.14. `vlade_wiki_write`

> Grava uma página OKF v0.2 na wiki de uma base. Use 'type' curto e descritivo. O frontmatter com generated e sources é criado pelo servidor.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "path", "type", "body"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": {"type": "string", "minLength": 1, "maxLength": 63},
    "path": {"type": "string", "minLength": 1, "maxLength": 256},
    "type": {"type": "string", "minLength": 1},
    "title": {"type": "string"},
    "description": {"type": "string"},
    "body": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "generated_by": {"type": "string"}
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["path", "type"],
  "properties": {
    "path": {"type": "string"},
    "type": {"type": "string"}
  }
}
```

Regras: `index.md` e `log.md` são nomes reservados. O servidor atualiza os dois arquivos depois de gravar a página.

### 5.15. `vlade_wiki_synthesize`

> Cria uma página de wiki sobre um tema a partir dos trechos recuperados da base. A página sai com citações ligadas aos documentos de origem.

Entrada:

```json
{
  "type": "object",
  "required": ["knowledge_base", "subject"],
  "additionalProperties": false,
  "properties": {
    "knowledge_base": {"type": "string", "minLength": 1, "maxLength": 63},
    "subject": {"type": "string", "minLength": 1, "maxLength": 4000},
    "path": {"type": "string", "minLength": 1, "maxLength": 256}
  }
}
```

Saída:

```json
{
  "type": "object",
  "required": ["path", "content"],
  "properties": {
    "path": {"type": "string"},
    "content": {"type": "string"}
  }
}
```

Regras: a ferramenta usa o modelo de geração da base. Sem trechos recuperados, devolve `invalid_argument`. As citações apontam para `vlade://kb/{slug}/documents/{id}#chunk/{id}`.

## 6. Resources

| URI | Template | Conteúdo | Tipo MIME |
|---|---|---|---|
| `vlade://kb/{slug}` | sim | Metadados da base e contagem de documentos | `application/json` |
| `vlade://kb/{slug}/documents/{document_id}` | sim | Metadados do documento e texto extraído, até 100000 caracteres | `application/json` |

Regras:

1. `resources/list` devolve só as bases do tenant. O servidor não lista os documentos, porque uma base pode ter milhões de documentos.
2. `resources/templates/list` devolve os dois templates.
3. Um URI de outro tenant devolve o mesmo erro de um URI inexistente.

## 7. Prompts

| Prompt | Argumentos | Mensagens geradas |
|---|---|---|
| `vlade_answer_with_citations` | `knowledge_base` (obrigatório), `question` (obrigatório) | Instrui o modelo a chamar `vlade_search`, responder só com as fontes e citar cada fonte |
| `vlade_summarize_document` | `knowledge_base` (obrigatório), `document_id` (obrigatório) | Instrui o modelo a ler o documento com `vlade_get_document` e resumir o documento com citações de página |

## 8. Limites de requisições

Valores padrão por chave. A configuração do tenant muda os valores.

| Grupo | Ferramentas | Limite |
|---|---|---|
| Leitura leve | `vlade_list_knowledge_bases`, `vlade_get_document`, `vlade_get_ingestion_status`, resources | 120 por minuto |
| Busca | `vlade_search` | 60 por minuto |
| Geração | `vlade_query` | 20 por minuto |
| Escrita | `vlade_ingest_document` | 30 por minuto |
| Administração | `vlade_delete_document`, `vlade_reindex_knowledge_base`, `vlade_evaluate` | 10 por minuto |

## 9. Erros

Erros de protocolo, como JSON inválido ou ferramenta desconhecida, usam os códigos JSON-RPC do MCP.

Erros de execução usam `isError: true`. O bloco de texto do resultado traz este JSON. O resultado de erro não traz `structuredContent`. O erro não é uma saída da ferramenta, e um cliente confere o `structuredContent` com o `outputSchema`. O MCP Inspector faz essa conferência:

```json
{
  "error": {
    "code": "not_found",
    "message": "A base de conhecimento 'vendas' não existe.",
    "retryable": false,
    "trace_id": "..."
  }
}
```

| Código | Significado | `retryable` |
|---|---|---|
| `invalid_argument` | Entrada inválida | `false` |
| `not_found` | Base, documento ou job não existe no tenant | `false` |
| `forbidden` | O papel da chave não permite a ferramenta | `false` |
| `write_tools_disabled` | O tenant não ativou as ferramentas de escrita | `false` |
| `conflict` | Estado incompatível | `false` |
| `quota_exceeded` | Cota do tenant esgotada | `false` |
| `rate_limited` | Limite de requisições atingido. A mensagem informa o tempo de espera | `true` |
| `unavailable` | Provedor ou banco indisponível | `true` |
| `internal` | Erro inesperado. A mensagem não contém detalhes internos | `true` |

## 10. Auditoria

Cada chamada grava um `AuditEvent`:

| Campo | Valor |
|---|---|
| `interface` | `mcp` |
| `action` | `mcp.tool_call`, `mcp.resource_read` ou `mcp.prompt_get` |
| `resource_type` | Nome da ferramenta, do resource ou do prompt |
| `outcome` | `success`, `denied`, `error` ou `preview` |
| `details` | Argumentos sem `content_text` e sem `query`. Hash SHA-256 de `query` e de `question`. Nome e versão do cliente MCP |

## 11. Configuração em clientes

### 11.1. Claude Code

Transporte HTTP:

```bash
claude mcp add --transport http vlade-rag https://rag.exemplo.com.br/mcp \
  --header "Authorization: Bearer ${VLADE_API_KEY}"
```

Transporte `stdio`:

```bash
claude mcp add vlade-rag --env VLADE_API_KEY=${VLADE_API_KEY} \
  --env VLADE_DATABASE__URL=${VLADE_DATABASE__URL} \
  -- vlade-rag mcp serve --transport stdio
```

### 11.2. Hermes Agent e outros clientes

Configure o servidor conforme a documentação do cliente. Use os mesmos valores: o comando `vlade-rag mcp serve --transport stdio` com a variável `VLADE_API_KEY`, ou a URL `/mcp` com o cabeçalho `Authorization`. Documentação do Hermes Agent: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp

### 11.3. Agent Skill

Instale a skill `skills/vlade-rag/` no cliente. A skill ensina o agente a escolher entre `vlade_search` e `vlade_query`, a ler as citações e a tratar `grounded: false`. A skill segue o padrão aberto Agent Skills.

A skill é uma pasta com o arquivo `SKILL.md`. Para instalar, copie a pasta `skills/vlade-rag/` para a pasta de skills do cliente:

| Cliente | Pasta de destino |
|---|---|
| Claude Code, só para você | `~/.claude/skills/vlade-rag/` |
| Claude Code, para um projeto | `.claude/skills/vlade-rag/` na raiz do projeto |
| Hermes Agent e outros clientes | Conforme a documentação do cliente |

A skill não tem credenciais nem endereços de servidor. O cliente guarda a chave de API e o endereço na configuração do servidor MCP (seção 11.1). A skill e o servidor MCP são independentes: instale os dois.

## 12. Testes

1. A CI roda o servidor com o MCP Inspector em modo CLI e chama cada ferramenta. O job `MCP server (Inspector)` executa `scripts/mcp_inspector.sh`. O script prepara um tenant e uma base e sobe o servidor por Streamable HTTP. Depois ele usa uma versão fixa do Inspector para conferir as ferramentas, os resources, os prompts, os erros, a chave inválida e a auditoria. O modo `--strict` do Inspector confere a portabilidade dos schemas. Para repetir o teste na sua máquina, defina `VLADE_DATABASE__OWNER_URL` e `VLADE_DATABASE__URL` e rode o script. O Inspector só roda no teste e não é dependência do pacote.
2. Um teste de contrato compara o `inputSchema` e o `outputSchema` de cada ferramenta com este documento.
3. O teste de isolamento chama cada ferramenta com a chave de um tenant e um recurso de outro tenant. O teste passa só se a resposta é `not_found`.
4. Antes de cada release, um teste manual usa pelo menos dois clientes diferentes, por exemplo Claude Code e Hermes Agent.

## 13. Versionamento do contrato

O contrato MCP usa versionamento semântico, separado da versão do pacote.

| Mudança | Versão |
|---|---|
| Campo opcional novo na entrada ou na saída | Minor |
| Ferramenta nova | Minor |
| Campo removido, campo renomeado, campo opcional que vira obrigatório, mudança de sentido | Major |

Uma mudança major mantém a ferramenta antiga por pelo menos uma versão minor, com aviso na descrição.
