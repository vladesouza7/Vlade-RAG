# ADR-0014: Sem human-in-the-loop na versão 1

- Status: Aceito
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D9

## Contexto

O LangGraph suporta interrupções e retomadas para aprovação humana. Essa função exige persistência do estado do grafo e uma interface de aprovação.

## Decisão

1. O fluxo de consulta da versão 1 não tem pausas para aprovação humana.
2. A confirmação de operações destrutivas usa o parâmetro `confirm` na API e no MCP. Essa confirmação não depende do LangGraph.
3. O grafo LangGraph usa uma estrutura que aceita um checkpointer depois, sem mudar os nós.

## Alternativas avaliadas

- **Human-in-the-loop na fase 3:** útil para respostas sensíveis, mas aumenta o escopo da fase 3.

## Consequências

- Uma aplicação que precisa de aprovação humana implementa a aprovação fora do Vlade-RAG na versão 1.
- Um ADR novo avalia a função depois da versão 1.
