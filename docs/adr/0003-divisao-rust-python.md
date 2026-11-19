# ADR-0003: Divisão entre Rust e Python e distribuição dos pacotes

- Status: Aceito
- Data: 2026-11-19

## Contexto

O rascunho original define Rust e Python como linguagens do núcleo, mas não define o papel de cada linguagem. Um binário Rust também não existe para todas as plataformas.

## Decisão

1. O Rust faz só trabalho de CPU puro e determinístico: normalização de texto, chunking, contagem de tokens, hash, deduplicação aproximada e fusão RRF.
2. O Rust não acessa rede, banco nem disco. O Python passa os dados ao Rust.
3. O Python faz I/O, integração com provedores e orquestração.
4. O projeto publica duas distribuições:
   - `vlade-rag`: Python puro, build com `hatchling`.
   - `vlade-rag-core`: motor Rust, build com `maturin`, wheels `abi3`.
5. `vlade-rag` instala `vlade-rag-core` pelo extra `native`. O extra `server` inclui `native`. As imagens Docker incluem `native`.
6. Cada função Rust tem uma implementação de reserva em Python puro. Um teste de propriedade compara as duas implementações.
7. Crates aprovados: `pyo3`, `tokenizers`, `text-splitter`, `unicode-normalization`, `blake3`.

## Alternativas avaliadas

- **Uma distribuição mista com maturin:** um pacote só. Mas a instalação falha em plataformas sem wheel e sem compilador Rust.
- **Rust com acesso ao banco:** menos cópias de dados. Mas duplica a lógica de acesso e de RLS em duas linguagens.
- **Só Python:** mais simples. Mas o chunking e a fusão ficam mais lentos em volume alto.

## Consequências

- O framework instala em qualquer plataforma com Python 3.12 ou mais recente.
- Sem o extra `native`, o framework fica mais lento, mas o resultado é igual.
- A CI de release compila wheels para as plataformas de RNF-09.
