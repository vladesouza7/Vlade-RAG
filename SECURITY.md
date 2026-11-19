# Política de segurança

## Versões com suporte

O projeto ainda não publicou uma versão estável. Só a versão mais recente do branch `main` recebe correções de segurança.

## Como relatar uma vulnerabilidade

Não abra uma issue pública para uma vulnerabilidade.

1. Abra um relato privado em [Security Advisories](https://github.com/vladesouza7/Vlade-RAG/security/advisories/new).
2. Descreva o problema, a versão ou o commit afetado e os passos para reproduzir o problema.
3. Se possível, informe o impacto e uma correção proposta.

## Prazos

| Etapa | Prazo |
|---|---|
| Confirmação do recebimento | Até 7 dias |
| Avaliação inicial | Até 14 dias |
| Correção de vulnerabilidade crítica | Até 30 dias depois da confirmação |

## Escopo

Temas com prioridade alta:

- Acesso a dados de outro tenant.
- Falhas de autenticação e de autorização na API, no MCP ou na CLI.
- Exposição de segredos em logs, traces ou respostas.
- Injeção de prompt que causa exposição de dados ou execução de operações de escrita.
- Download de URL que alcança endereços internos (SSRF).

Fora do escopo: vulnerabilidades em serviços externos (PostgreSQL, Valkey, Kestra, Langfuse, Grafana) sem relação com a configuração que o Vlade-RAG entrega. Relate esses casos ao projeto do serviço.
