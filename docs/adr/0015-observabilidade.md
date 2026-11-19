# ADR-0015: Observabilidade com OpenTelemetry, Langfuse e LGTM

- Status: Aceito
- Data: 2026-11-19

## Contexto

O Vlade-RAG precisa de dois tipos de observabilidade. A observabilidade de infraestrutura mostra latência, erros, memória e logs. A observabilidade de IA mostra prompts, modelos, tokens, custo, documentos recuperados e qualidade.

## Decisão

1. O código usa OpenTelemetry para traces, métricas e logs.
2. O Langfuse recebe os traces de IA pelo SDK Langfuse, que usa OpenTelemetry. O Langfuse também guarda os prompts versionados e os experimentos de avaliação.
3. O Grafana Alloy coleta a telemetria e envia ao Prometheus, ao Loki e ao Tempo. O Grafana mostra os dashboards. O projeto não usa o Grafana Agent, que chegou ao fim de vida.
4. O Kestra envia métricas Prometheus e traces OpenTelemetry ao mesmo coletor.
5. Sem Langfuse configurado, o sistema funciona e só deixa de enviar dados ao Langfuse.
6. `tenant_id` fica nos traces e nos logs, não nos rótulos de métricas.

## Alternativas avaliadas

- **Só Langfuse:** cobre a IA, mas não cobre a infraestrutura.
- **Só a stack LGTM:** cobre a infraestrutura, mas não tem análise de prompts e de avaliações.
- **Fornecedor SaaS único:** menos operação, mas cria dependência de fornecedor.

## Consequências

- O perfil `prod` precisa de memória para a stack LGTM e para o Langfuse. Esses serviços ficam fora do perfil `dev`.
- Grafana, Loki e Tempo usam AGPL-3.0. São serviços externos sem modificação (ADR-0001).
