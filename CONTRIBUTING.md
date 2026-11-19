# Como contribuir

Obrigado pelo interesse no Vlade-RAG. Este guia explica como preparar o ambiente, como verificar uma mudança e como enviar um pull request.

## Antes de começar

1. Leia o [`VLADE-RAG.md`](VLADE-RAG.md) e o [`docs/ROADMAP.md`](docs/ROADMAP.md).
2. Para uma mudança grande, abra uma issue antes de escrever código. Descreva o problema e a solução proposta.
3. Para uma decisão de arquitetura nova, proponha um ADR em `docs/adr/`. Use o modelo de [`docs/adr/README.md`](docs/adr/README.md).

## Ambiente

Requisitos: uv, Docker com Compose. Rust estável é opcional.

```bash
uv sync --package vlade-rag --extra api --extra cli
```

Para instalar também o motor nativo, instale o Rust e acrescente `--extra native`:

```bash
uv sync --package vlade-rag --extra api --extra cli --extra native
```

## Verificações

Rode as mesmas verificações da CI antes de enviar um pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-fail-under=85
```

Se você mudou código Rust:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace --no-default-features
```

Se você mudou documentação:

```bash
python3 .claude/skills/asd-ste100-pt-br/scripts/ste-lint-ptbr.py --disable rotacao-de-sinonimos <arquivo>
```

## Regras

| Tema | Regra |
|---|---|
| Idioma do código | Inglês: código, identificadores, mensagens de log, mensagens de commit |
| Idioma da documentação | Português do Brasil, sem violações duras no linter ASD-STE100 pt-BR ([ADR-0009](docs/adr/0009-idiomas-do-projeto.md)) |
| Commits | [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` |
| Branches | `feat/<tema>`, `fix/<tema>`, `docs/<tema>` |
| Camadas | O `core` não importa outras camadas. Um teste verifica essa regra ([ADR-0002](docs/adr/0002-arquitetura-ports-adapters.md)) |
| Adapters | Escreva o teste de contrato do port antes do adapter |
| Dependências | Verifique a licença contra o [ADR-0001](docs/adr/0001-licenca-mit.md). O núcleo aceita só licenças permissivas |
| Segredos | Nunca faça commit de segredos. Use `.env`, que o Git ignora |
| Testes com LLM real | Marque com `@pytest.mark.llm`. A CI padrão não roda esses testes |

## Pull requests

1. Crie um branch a partir de `main`.
2. Faça uma mudança por pull request.
3. Preencha o modelo do pull request.
4. Espere a CI passar.
5. Responda aos comentários da revisão.

## Licença das contribuições

O projeto usa a licença MIT. Quando você envia uma contribuição, você concorda em licenciar a contribuição sob a mesma licença.
