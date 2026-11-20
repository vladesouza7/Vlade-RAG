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

Licenças verificadas: pendente. Verifique na tarefa 1.11 do roadmap.

## Alternativas avaliadas

- **`nomic-embed-text`:** leve, mas com foco em inglês.
- **`multilingual-e5-large`:** boa qualidade multilíngue. Fica como alternativa no benchmark da fase 3.
- **Embeddings de API paga como padrão:** boa qualidade, mas o padrão exigiria chave e custo.

## Consequências

- O perfil `dev` depende de um Ollama com o modelo `bge-m3`. O Ollama roda fora do Compose.
- O benchmark da fase 3 compara `bge-m3` com pelo menos um modelo alternativo no dataset em pt-BR.
