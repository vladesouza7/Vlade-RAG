# ADR-0007: Valkey como cache padrão

- Status: Aceito
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D3

## Contexto

O Vlade-RAG usa cache para embeddings de consulta, resultados de busca e limite de requisições. A licença do servidor Redis deixou de ser permissiva a partir da versão 7.4. O Valkey é um fork do Redis com licença BSD-3-Clause e usa o mesmo protocolo.

## Decisão

1. O port `Cache` é genérico.
2. A imagem padrão dos perfis do Compose é o Valkey.
3. O adapter usa o cliente `redis-py` (MIT), compatível com Valkey e com Redis.
4. Sem cache configurado, o sistema usa um cache em memória por processo.

## Alternativas avaliadas

- **Redis:** mesmo protocolo, mas a licença do servidor não segue a política do ADR-0001 para a imagem padrão.
- **Sem cache:** mais simples, mas o limite de requisições fica por processo e o custo de embeddings de consulta aumenta.

## Consequências

- Quem já usa Redis aponta `VLADE_CACHE__URL` para o Redis sem mudar código.
