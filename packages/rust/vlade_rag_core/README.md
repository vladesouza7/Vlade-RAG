# vlade-rag-core

Motor nativo (Rust) do [Vlade-RAG](https://github.com/vladesouza7/Vlade-RAG).

Instale pelo extra `native` do pacote principal:

```bash
pip install "vlade-rag[native]"
```

O motor faz só trabalho de CPU: normalização de texto, chunking, contagem de tokens, hash e fusão RRF. O pacote `vlade-rag` funciona sem este motor, com uma implementação em Python puro. Veja o [ADR-0003](https://github.com/vladesouza7/Vlade-RAG/blob/main/docs/adr/0003-divisao-rust-python.md).

Licença: MIT.
