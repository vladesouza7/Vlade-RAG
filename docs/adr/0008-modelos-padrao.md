# ADR-0008: Modelos padrão de embeddings e de reranking

- Status: Aceito. Item 2 complementado pelo ADR-0018
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D4, D5

## Contexto

A qualidade em português do Brasil varia muito entre modelos. O framework precisa de valores padrão que funcionam localmente e em pt-BR.

## Decisão

1. Modelo de embeddings padrão: `bge-m3`. O modelo é multilíngue e gera vetores de 1024 dimensões. O adapter padrão chama o modelo pelo Ollama. O adapter `sentence-transformers` também aceita o modelo (`BAAI/bge-m3`).
2. Reranker padrão: `BAAI/bge-reranker-v2-m3`, multilíngue, pelo adapter `sentence-transformers` (classe `CrossEncoder`).
3. O reranking fica desligado por padrão até a fase 3.
4. Antes de usar cada modelo, verifique a licença do modelo no cartão do modelo e registre a licença nesta página.

Licenças verificadas em 2026-11-20, no cartão do modelo e no PyPI:

| Item | Licença |
|---|---|
| `BAAI/bge-reranker-v2-m3` (reranker local) | Apache-2.0 |
| `sentence-transformers` 6.3.0 | Apache-2.0 |

Pendentes: o `bge-m3`, o PyTorch e os cinco modelos de reranking por API do ADR-0018. O PyTorch e, no Linux, as bibliotecas NVIDIA CUDA que ele traz ficam no extra `local-models`, fora da instalação padrão (ADR-0001, item 4).

## Alternativas avaliadas

- **`nomic-embed-text`:** leve, mas com foco em inglês.
- **`multilingual-e5-large`:** boa qualidade multilíngue. Fica como alternativa no benchmark da fase 3.
- **Embeddings de API paga como padrão:** boa qualidade, mas o padrão exigiria chave e custo.

## Consequências

- O perfil `dev` depende de um Ollama com o modelo `bge-m3`. O Ollama roda fora do Compose.
- O benchmark da fase 3 compara `bge-m3` com pelo menos um modelo alternativo no dataset em pt-BR.

Atualização de 2026-11-20 (adapter local do reranker):

- O `bge-reranker-v2-m3` tem 567.755.777 parâmetros em ponto flutuante de 32 bits. Os pesos ocupam cerca de 2,3 GB de memória. O RNF-11 limita todo o perfil `dev` a 3 GB, então o reranker local não é ligado no perfil `dev`.
- O adapter está em `vlade_rag.reranking.local`. Ele carrega o modelo na primeira chamada, uma única vez por processo, e roda o carregamento e a pontuação em uma thread, para não parar o laço de eventos.
- A pontuação depende do modelo. Compare os escores só dentro de uma lista.
- Ninguém mediu a qualidade nem a latência do `bge-reranker-v2-m3` neste projeto. A máquina de desenvolvimento não roda modelos locais. O teste com o modelo real fica desligado por padrão (`tests/integration/test_local_reranker_model.py`).
