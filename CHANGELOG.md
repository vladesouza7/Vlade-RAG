# Changelog

Este arquivo registra as mudanças relevantes de cada versão. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). O projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- Especificação mestre (`VLADE-RAG.md`), documentos fundadores e ADRs 0001 a 0015.
- Workspace `uv` com o pacote `vlade-rag` e workspace Cargo com o motor `vlade-rag-core`.
- Esqueleto dos módulos da arquitetura.
- Configuração tipada por variáveis `VLADE_*`.
- Endpoint `GET /health/live`.
- CLI `vlade-rag` com os comandos `version` e `api serve`.
- Ponte com o motor nativo e implementação de reserva em Python.
- CI: ruff, mypy, pytest com cobertura mínima de 85%, clippy, rustfmt, build das distribuições, verificação de licenças, linter de documentação e teste do Compose.
- Docker Compose com o perfil `dev`: API, PostgreSQL 17 com pgvector, Valkey.
- Arquivos de projeto open source: `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, modelos de issue e de pull request.
