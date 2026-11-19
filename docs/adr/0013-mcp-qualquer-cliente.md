# ADR-0013: MCP como interface de primeira classe para qualquer cliente

- Status: Aceito
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D8

## Contexto

O Vlade-RAG deve servir agentes de IA além de aplicações REST. O rascunho cita Claude Code e Hermes Agent. Os dois são clientes MCP. O Hermes Agent (Nous Research, MIT) consome servidores MCP e usa skills no padrão aberto Agent Skills, o mesmo formato do Claude Code.

## Decisão

1. O MCP tem o mesmo nível da API REST. As duas interfaces chamam os mesmos casos de uso.
2. O servidor segue só a especificação do MCP. O servidor não tem código específico para um cliente.
3. Transportes: `stdio` e Streamable HTTP.
4. Nomes de ferramentas em `snake_case` com o prefixo `vlade_`.
5. Ferramentas de leitura ativas por padrão. Ferramentas de escrita ativas por configuração do tenant. Ferramentas destrutivas exigem `confirm: true`.
6. O projeto publica a Agent Skill `skills/vlade-rag/` no padrão aberto Agent Skills.
7. O contrato completo está no `MCP_SPEC.md`.

## Alternativas avaliadas

- **MCP depois da versão 1:** menos escopo inicial, mas o rascunho define o MCP como recurso de primeira classe.
- **Servidor MCP como projeto separado:** independência de release, mas duplica autenticação e auditoria.

## Consequências

- A CI testa o servidor com o MCP Inspector.
- Cada release tem um teste manual com pelo menos dois clientes diferentes.
- Uma mudança na especificação do MCP exige atualização do SDK e do `MCP_SPEC.md`.
