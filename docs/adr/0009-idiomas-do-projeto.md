# ADR-0009: Idiomas do código e da documentação

- Status: Aceito
- Data: 2026-11-19

## Contexto

O mantenedor e o público inicial falam português do Brasil. O código de um framework open source é lido por contribuidores de outros países. Agentes de IA leem a documentação e as descrições de ferramentas sem ninguém para tirar dúvidas.

## Decisão

1. Código, identificadores, nomes de tabelas, mensagens de log e mensagens de commit usam inglês.
2. A documentação do repositório usa português do Brasil.
3. A documentação passa no linter da skill `asd-ste100-pt-br` sem violações duras. Requisitos, procedimentos, descrições de ferramentas e mensagens de erro usam o modo Estrito. Prosa explicativa usa o modo Flexível.
4. Os prompts padrão de geração existem em pt-BR e em inglês.
5. As descrições das ferramentas MCP usam pt-BR na versão 1. Uma versão em inglês entra quando o projeto tiver contribuidores de outros idiomas.

## Alternativas avaliadas

- **Tudo em inglês:** alcance maior, mas afasta o público inicial.
- **Tudo em português:** acessível ao público inicial, mas o código fica difícil para contribuidores de outros países.

## Consequências

- A CI roda o linter de documentação em `docs/` e `skills/`.
- Um README em inglês pode existir como resumo, sem substituir a documentação em pt-BR.
