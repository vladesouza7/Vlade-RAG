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

1. Preencha `GRAFANA_ADMIN_PASSWORD` no `.env`. O Compose usa `admin` quando a variável está vazia; troque no perfil `prod`.
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

5. Abra o Grafana em `http://127.0.0.1:3000` e use o usuário `admin` com a senha do `.env`.

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

Os limites somam cerca de 2,4 GB: Alloy 256 MiB, Prometheus 512 MiB, Loki 384 MiB, Tempo 384 MiB, Grafana 384 MiB, `cadvisor` 192 MiB e os três exporters 96 MiB cada. O perfil `prod` completo precisa de mais memória do que o perfil `dev`, porque soma a API, o worker, o MCP, o PostgreSQL, o Valkey e o RustFS.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `alloy/config.alloy` | Receptor OTLP, escrita remota, traces para o Tempo, logs do Docker para o Loki |
| `prometheus/prometheus.yml` | Jobs de coleta e escrita remota |
| `prometheus/rules/` | Regras de alerta (tarefa 4.6) |
| `loki/local-config.yaml` | Loki em binário único, com armazenamento em disco |
| `tempo/tempo.yml` | Tempo em binário único, com armazenamento local |
| `grafana/provisioning/datasources/` | Fontes de dados do Grafana |
| `grafana/provisioning/dashboards/` | Provedor dos dashboards |
| `grafana/dashboards/` | Os cinco dashboards (tarefa 4.6) |
