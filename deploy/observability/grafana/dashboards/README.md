# Dashboards

O provedor do Grafana lê os arquivos JSON desta pasta e os coloca na pasta `Vlade-RAG`. Cada arquivo define um `uid` fixo para os links entre os dashboards.

| Arquivo | UID | Título |
|---|---|---|
| `rag-performance.json` | `rag-performance` | RAG Performance |
| `llm-observability.json` | `llm-observability` | LLM Observability |
| `retrieval-analytics.json` | `retrieval-analytics` | Retrieval Analytics |
| `infrastructure.json` | `infrastructure` | Infrastructure |
| `workflow-monitoring.json` | `workflow-monitoring` | Workflow Monitoring |

Os painéis de Prometheus usam a fonte `prometheus`. Os painéis de log usam a fonte `loki`, e o painel de traces usa a fonte `tempo`. Para ver dados, ligue `VLADE_OTEL__ENABLED=true` na aplicação e aponte `VLADE_OTEL__ENDPOINT` para o Alloy. O script `scripts/observability/seed_telemetry.py` gera dados de demonstração sem provedor externo.
