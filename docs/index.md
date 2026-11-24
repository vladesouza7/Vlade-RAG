# Vlade-RAG

Vlade-RAG é um framework open source de Retrieval-Augmented Generation. O núcleo reutilizável faz ingestão, indexação, recuperação, geração com citações e avaliação. Uma aplicação troca provedores por configuração: LLM, embeddings, reranker, banco vetorial, chunking e fontes de documentos.

O projeto não é um chatbot. Ele entrega a base para aplicações com uma base de conhecimento isolada por tenant.

## Comece por aqui

| Documento | Conteúdo |
|---|---|
| [Requisitos](PROJECT_SPEC.md) | Casos de uso, requisitos funcionais e não funcionais |
| [Arquitetura](ARCHITECTURE.md) | Ports, adapters, pipeline, persistência e interfaces |
| [Contrato do MCP](MCP_SPEC.md) | Ferramentas, papéis, limites e transportes |
| [Roadmap](ROADMAP.md) | Fases, tarefas e situação atual |
| [Guia de implantação](operacao/implantacao.md) | Perfis do Compose, variáveis, operação e solução de problemas |

## Decisões de arquitetura

As decisões aceitas estão no [índice de ADRs](adr/README.md). Cada ADR registra contexto, decisão, alternativas e consequências. ADRs aceitos não mudam: uma mudança cria um ADR novo.

## Observabilidade e operação

A pilha de observabilidade usa Grafana Alloy, Prometheus, Loki, Tempo e Grafana no perfil `prod` do Compose. O [guia de implantação](operacao/implantacao.md) descreve os serviços, os segredos e os dashboards. O [README da pilha](https://github.com/vladesouza7/Vlade-RAG/blob/homolog/deploy/observability/README.md) lista portas, retenção e alertas.

## Código e licença

O repositório está no [GitHub](https://github.com/vladesouza7/Vlade-RAG). O código usa licença MIT. Dependências com licença diferente ficam em extras opcionais, conforme a [política de licenças](adr/0001-licenca-mit.md).
