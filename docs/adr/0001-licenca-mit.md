# ADR-0001: Licença MIT e política de licenças das dependências

- Status: Aceito
- Data: 2026-11-19

## Contexto

O Vlade-RAG é um framework para outros projetos, inclusive projetos comerciais. A licença do framework e as licenças das dependências definem quem pode usar o framework e com que obrigações.

## Decisão

1. O Vlade-RAG é open source, com licença MIT.
2. O núcleo e a instalação padrão usam só dependências com licença permissiva: MIT, BSD, Apache-2.0, ISC, PSF, Unlicense, Zlib, CC0.
3. Uma dependência com licença MPL-2.0 é aceita e fica registrada nesta página.
4. Uma dependência com licença GPL, LGPL, AGPL, SSPL, BUSL, RSAL ou outra licença não permissiva fica só em um extra opcional, com aviso no README do extra.
5. Um serviço externo que roda em processo separado não entra no pacote Python. A documentação de implantação informa a licença do serviço.
6. A CI verifica as licenças com `pip-licenses` (Python) e `cargo-deny` (Rust).

Dependências registradas com licença MPL-2.0: nenhuma.

## Alternativas avaliadas

- **Apache-2.0:** dá concessão explícita de patentes. O mantenedor escolheu a MIT pela simplicidade e pela compatibilidade ampla.
- **AGPL-3.0:** protege contra uso fechado em serviços, mas impede a adoção em muitos produtos comerciais.

## Consequências

- O driver `psycopg` (LGPL-3.0) fica fora do núcleo. O adapter PostgreSQL usa `asyncpg` (Apache-2.0). Veja o ADR-0004.
- O `pg_search` (AGPL-3.0) é opcional. Veja o ADR-0005.
- O PyMuPDF (AGPL-3.0) fica fora do núcleo. Veja o ADR-0010.
- MinIO, Grafana, Loki e Tempo (AGPL-3.0) são serviços externos sem modificação. O pacote não inclui esses serviços.
- O projeto precisa de `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` e `SECURITY.md`.
