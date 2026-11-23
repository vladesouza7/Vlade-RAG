# Observabilidade

A pilha LGTM da fase 4 (ADR-0015). Os serviços rodam no perfil `prod` do Compose, com exceção do Alloy, que também roda no perfil `staging`.

## Fluxo

```text
API, worker e MCP --OTLP HTTP 4318--> Alloy
Alloy --remote write--> Prometheus
Alloy --OTLP gRPC-----> Tempo
Logs do Docker -------> Alloy --> Loki
Grafana ---------------- consulta Prometheus, Loki e Tempo
```

O Alloy recebe as métricas e os traces em `4318` (HTTP) e `4317` (gRPC). As métricas viram escrita remota no Prometheus. Os traces vão para o Tempo. Os logs saem do `stdout` dos containers, passam pelo `loki.source.docker` e chegam ao Loki.

## Serviços

| Serviço | Perfil | Porta no host | Função |
|---|---|---|---|
| `alloy` | `staging`, `prod` | `4317`, `4318`, `12345` | Coletor OTLP e de logs |
| `prometheus` | `prod` | `9090` | Métricas, com escrita remota ligada |
| `loki` | `prod` | `3100` | Logs |
| `tempo` | `prod` | `3200` | Traces |
| `grafana` | `prod` | `3000` | Dashboards |
| `node-exporter` | `prod` | `9100` | CPU, memória e disco do host |
| `cadvisor` | `prod` | `8080` | CPU e memória dos containers |
| `postgres-exporter` | `prod` | `9187` | Estatísticas do PostgreSQL |
| `redis-exporter` | `prod` | `9121` | Estatísticas do Valkey |

Todas as portas escutam em `127.0.0.1`. Para expor a interface do Grafana, use um proxy reverso com autenticação. Não publique as portas do Prometheus, do Loki e do Tempo.

## Como subir

1. Preencha `GRAFANA_ADMIN_PASSWORD` no `.env`. O Compose usa `admin` quando a variável está vazia. Troque a senha no perfil `prod`.
2. Ligue a telemetria da aplicação:

   ```bash
   VLADE_OTEL__ENABLED=true
   VLADE_OTEL__ENDPOINT=http://alloy:4318
   ```

3. Suba a pilha:

   ```bash
   docker compose --profile prod up -d
   ```

4. Confira os serviços:

   ```bash
   curl -fsS http://127.0.0.1:9090/-/ready
   curl -fsS http://127.0.0.1:3100/ready
   curl -fsS http://127.0.0.1:3200/ready
   curl -fsS http://127.0.0.1:3000/api/health
   ```

5. Abra o Grafana em `http://127.0.0.1:3000` e use o usuário `admin` com a senha do `.env`. A pasta `Vlade-RAG` tem os cinco dashboards.

## Métricas da aplicação

O código registra as métricas da tabela 16.2 da arquitetura por OTLP. O Alloy converte as métricas em escrita remota no Prometheus. O custo em `vlade_llm_cost_usd_total` vem de uma tabela pequena de preços. Um modelo fora da tabela custa zero. `tenant_id` nunca entra em rótulo de métrica.

Para gerar dados de demonstração sem provedor externo, rode `scripts/observability/seed_telemetry.py` com `VLADE_OTEL__ENABLED=true`, `VLADE_OTEL__ENDPOINT=http://127.0.0.1:4318`, `VLADE_STORAGE__BACKEND=memory` e `VLADE_OBJECT_STORAGE__BACKEND=memory`. O script cria uma base com hashing e LLM extrativo, ingere documentos, faz buscas, responde perguntas e roda uma avaliação.

## Dashboards

| UID | Título | Dados principais |
|---|---|---|
| `rag-performance` | RAG Performance | Latência e vazão de consultas, respostas fundamentadas, duração das etapas, avaliações e traces |
| `llm-observability` | LLM Observability | Tokens, custo estimado, erros de geração e falhas de provedor |
| `retrieval-analytics` | Retrieval Analytics | Resultados por retriever, latência de recuperação e de reranking, logs |
| `infrastructure` | Infrastructure | CPU, memória, disco, conexões do PostgreSQL e clientes do Valkey |
| `workflow-monitoring` | Workflow Monitoring | Fila de ingestão, jobs por status, duração das etapas e alertas |

O Grafana lê os arquivos JSON de `grafana/dashboards/` e os coloca na pasta `Vlade-RAG`. Os painéis que mostram falhas ficam vazios quando não há falhas: é o estado normal.

## Alertas

As oito regras em `prometheus/rules/alerts.yml` cobrem falhas de ingestão, latência de recuperação, erros de geração e falhas de provedor. Outras regras cobrem fila em crescimento, PostgreSQL indisponível, memória baixa e queda na qualidade das avaliações. Cada regra tem um teste de falha provocada em `tests/promtool/alerts.test.yml`. A CI roda o `promtool test rules`. A CI falha se um alerta não disparar.

```bash
docker run --rm --entrypoint promtool -v "$PWD:/repo:ro" \
  prom/prometheus:v3.16.0 test rules /repo/tests/promtool/alerts.test.yml
```

## Retenção

| Sinal | Retenção | Configuração |
|---|---|---|
| Métricas | 15 dias | `PROMETHEUS_RETENTION` |
| Logs | 7 dias | `LOKI_RETENTION` (arquivo `loki/local-config.yaml`) |
| Traces | 48 horas | `TEMPO_BLOCK_RETENTION` (arquivo `tempo/tempo.yml`) |

O volume de traces é o que mais cresce. Aumente a retenção só depois de medir o disco.

## Staging

No perfil `staging`, só o Alloy sobe entre os serviços de observabilidade. Aponte as três URLs para os backends externos:

```bash
PROMETHEUS_REMOTE_WRITE_URL=https://prometheus.exemplo/api/v1/write
LOKI_PUSH_URL=https://loki.exemplo/loki/api/v1/push
TEMPO_OTLP_ENDPOINT=tempo.exemplo:4317
```

O endpoint do Tempo usa gRPC sem TLS por padrão. Para um backend externo com TLS, ajuste o bloco `otelcol.exporter.otlp "tempo"` em `alloy/config.alloy`.

## Segurança

- O Alloy lê o socket do Docker. Quem escreve no socket controla o host. Mantenha o socket somente leitura e restrinja o acesso ao arquivo do Compose.
- O `postgres-exporter` usa o papel `vlade_owner`. Para produção, crie um papel `vlade_monitor` com `pg_monitor` e troque o `DATA_SOURCE_NAME`.
- O `cadvisor` roda como privilegiado. Ele lê os cgroups e o socket do Docker. Se a política da máquina não permitir, remova o serviço e o job `cadvisor` do Prometheus. O dashboard de infraestrutura perde as métricas por container.
- O Grafana começa com o usuário `admin` e a senha `admin` quando `GRAFANA_ADMIN_PASSWORD` está vazia. Troque a senha no `.env` antes de subir o perfil `prod`.

## Memória

Os limites somam cerca de 2,4 GB. Alloy usa 256 MiB. Prometheus usa 512 MiB. Loki, Tempo e Grafana usam 384 MiB cada. O `cadvisor` usa 192 MiB e os três exporters usam 96 MiB cada. O perfil `prod` completo precisa de mais memória do que o perfil `dev`, porque soma a API, o worker, o MCP, o PostgreSQL, o Valkey e o RustFS.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `alloy/config.alloy` | Receptor OTLP, escrita remota, traces para o Tempo, logs do Docker para o Loki |
| `prometheus/prometheus.yml` | Jobs de coleta e escrita remota |
| `prometheus/rules/alerts.yml` | Oito regras de alerta |
| `loki/local-config.yaml` | Loki em binário único, com armazenamento em disco |
| `tempo/tempo.yml` | Tempo em binário único, com armazenamento local |
| `grafana/provisioning/datasources/` | Fontes de dados do Grafana |
| `grafana/provisioning/dashboards/` | Provedor dos dashboards |
| `grafana/dashboards/` | Os cinco dashboards provisionados |
