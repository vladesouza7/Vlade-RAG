# ADR-0002: Clean Architecture com ports e adapters

- Status: Aceito
- Data: 2026-11-19

## Contexto

O Vlade-RAG precisa trocar provedores de LLM, embeddings, reranking, banco vetorial e armazenamento sem mudar a aplicação. O núcleo também precisa funcionar como biblioteca, sem servidor.

## Decisão

1. O código segue Clean Architecture: domínio, aplicação (casos de uso), adapters e interfaces.
2. Cada serviço externo fica atrás de um port (`typing.Protocol`).
3. Um ponto de composição cria os adapters a partir da configuração e injeta os adapters nos casos de uso.
4. Um pacote externo registra adapters novos pelo grupo de entry points `vlade_rag.plugins`.
5. Cada port tem uma suíte de testes de contrato pública em `vlade_rag.testing.contracts`.
6. O núcleo funciona sem LangGraph, Kestra, MCP e FastAPI. Essas camadas chamam os casos de uso.

## Alternativas avaliadas

- **Construir sobre LangChain ou LlamaIndex:** acelera o início. Mas acopla o domínio a abstrações externas que mudam com frequência, e limita o controle sobre multi-tenancy e observabilidade.
- **Arquitetura em camadas sem ports:** mais simples, mas a troca de provedor exige mudar os casos de uso.

## Consequências

- Mais código de interface no início.
- Os testes de casos de uso rodam com adapters em memória, sem rede.
- Um contribuidor externo cria um adapter sem mudar o repositório principal.
