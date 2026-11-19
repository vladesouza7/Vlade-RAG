# Vlade-RAG — regras para agentes

## Documentos

| Documento | Uso |
|---|---|
| `VLADE-RAG.md` | Prompt mestre e fonte de verdade |
| `docs/PROJECT_SPEC.md` | Requisitos com IDs (RF, RNF, UC) |
| `docs/ARCHITECTURE.md` | Ports, esquema SQL, pipelines, interfaces |
| `docs/MCP_SPEC.md` | Contrato do servidor MCP |
| `docs/ROADMAP.md` | Fases, tarefas, critérios de aceite, situação |
| `docs/adr/` | Decisões de arquitetura |

## Regras

- Leia `VLADE-RAG.md` antes de qualquer tarefa.
- Se `VLADE-RAG.md` e um documento em `docs/` se contradizem, `VLADE-RAG.md` vale. Corrija o documento em `docs/` e informe o usuário.
- Antes de começar uma tarefa do roadmap, leia a seção do `ARCHITECTURE.md` e o ADR citados na tarefa.
- Escreva o código, os identificadores e as mensagens de log em inglês.
- Escreva a documentação em português do Brasil.
- Revise cada documento novo em português com a skill `asd-ste100-pt-br` (instalada em `.claude/skills/`). Use o modo Estrito para requisitos, procedimentos, descrições de ferramentas MCP e mensagens de erro. Use o modo Flexível para prosa explicativa.
- Verifique um documento com o linter da skill:
  `python3 .claude/skills/asd-ste100-pt-br/scripts/ste-lint-ptbr.py --disable rotacao-de-sinonimos <arquivo>`
- Registre cada decisão de arquitetura nova como ADR em `docs/adr/` e atualize `docs/adr/README.md`.
- O projeto é open source com licença MIT. Antes de acrescentar uma dependência, verifique a licença dela contra a seção 16.1 do `VLADE-RAG.md` e o ADR-0001.
- Quando concluir uma tarefa do roadmap, atualize a situação em `docs/ROADMAP.md`.
- O rascunho original está em `docs/referencia/VLADE-RAG.original.md`. Não edite esse arquivo.
