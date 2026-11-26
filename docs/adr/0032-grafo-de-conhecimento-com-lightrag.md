# ADR-0032: Grafo de conhecimento com LightRAG

- Status: Aceito
- Data: 2026-11-25

## Contexto

A busca híbrida responde bem a perguntas sobre um trecho. Ela responde pior a perguntas que comparam autores, conceitos ou eventos espalhados por muitos documentos. Um grafo de entidades e de relações ajuda nesse tipo de pergunta (GraphRAG).

O mantenedor escolheu o LightRAG (`lightrag-hku`, licença MIT). O `microsoft/graphrag` ficou fora: o projeto está em modo de manutenção, grava em Parquet e LanceDB e não usa PostgreSQL.

A prova técnica da tarefa 6.0 (`scripts/spikes/lightrag_spike.py`) rodou com o LightRAG 1.5.8 no PostgreSQL 17 do projeto, sem modelo local. Os seis itens passaram:

1. `PGKVStorage`, `PGVectorStorage`, `PGTableGraphStorage` e `PGDocStatusStorage` funcionam numa base separada. O `PGTableGraphStorage` usa tabelas comuns e não precisa da extensão Apache AGE.
2. `ainsert_custom_chunks` grava o texto de cada trecho sem mudança. O hash SHA-256 do texto liga o trecho do LightRAG ao trecho do Vlade-RAG.
3. Dois `workspace` na mesma base não se enxergam.
4. `adelete_by_doc_id` remove as entidades, as relações e os trechos do documento e não afeta outro workspace.
5. `aquery_data` devolve entidades, relações e trechos sem gerar a resposta.
6. Nenhum pacote é instalado durante a execução. O `pipmaster` do LightRAG só instala o `asyncpg` e o `pgvector` quando eles faltam, e o extra `graph` instala os dois.

## Decisão

1. O port novo `GraphIndex` tem três operações: `index_document`, `delete_document` e `search`. O núcleo não importa o LightRAG (ADR-0002).
2. O adapter `LightRAGGraphIndex` fica no extra `graph`. O adapter `MemoryGraphIndex` serve para testes: ele não chama LLM.
3. O grafo fica numa base de dados própria (`vlade_graph`) com um papel próprio (`vlade_graph`). A variável `VLADE_GRAPH__DATABASE_URL` liga o grafo no servidor. Sem ela, nenhuma base consegue ligar o grafo.
4. Cada base tem um workspace `t<tenant>_k<base>`. O adapter calcula o workspace a partir do contexto da chamada e do id da base. Uma entrada do usuário nunca define o workspace.
5. O grafo fica desligado por padrão em cada base (`graph.enabled = false`). O grafo usa um modelo de extração próprio (`graph.provider`, `graph.model`), separado do modelo de resposta.
6. A ingestão enfileira um job `graph_index` depois da publicação de uma versão. O job troca a versão antiga do documento pela nova no grafo. Uma falha no job do grafo não marca a versão como falha: a busca vetorial da versão continua válida.
7. O retriever `graph` entra na fusão RRF com os outros retrievers. O retriever só devolve trechos publicados que passam no filtro de metadados (`published_chunks`).
8. A rota `POST /v1/knowledge-bases/{kb}/graph/search` e a ferramenta MCP `vlade_search_graph` mostram entidades, relações e trechos. A rota `POST /v1/knowledge-bases/{kb}/graph/reindex` enfileira um job por documento publicado.
9. O vetor de cada modelo de embeddings fica em tabelas próprias do LightRAG (`model_name` no `EmbeddingFunc`).

## Alternativas avaliadas

- **`microsoft/graphrag`:** em modo de manutenção, sem PostgreSQL, custo alto de indexação.
- **Grafo implementado no projeto:** controle total e RLS, mas reescreve a extração, a deduplicação de entidades e os modos de consulta que o LightRAG já tem.
- **`PGGraphStorage` com Apache AGE:** o próprio LightRAG marca esse armazenamento como obsoleto. Ele exige uma imagem PostgreSQL com AGE.

## Consequências

- O isolamento do grafo depende do código: o LightRAG separa os dados por uma coluna `workspace`, sem a segunda barreira do RLS. A base separada e o papel separado limitam o alcance de um erro. Um teste automatizado verifica o isolamento pela API, pelo MCP e direto no adapter.
- O LightRAG lê a conexão do PostgreSQL de variáveis de ambiente do processo (`POSTGRES_*`) e usa um pool único por processo. O adapter define essas variáveis a partir de `VLADE_GRAPH__DATABASE_URL`. Um processo usa uma só base de grafo.
- O LightRAG grava um arquivo de controle no diretório de trabalho (`VLADE_GRAPH__WORKING_DIR`). O Compose monta um volume para esse diretório.
- A extração chama o LLM em cada trecho. O projeto LightRAG recomenda um modelo com pelo menos 32B de parâmetros, contexto de 32k e sem modo "thinking". Cada consulta também chama o LLM para extrair palavras-chave. O custo e a latência são maiores que os da busca híbrida.
- `ainsert_custom_chunks` está marcado como API legada no LightRAG 1.5.8. Um teste de integração (`tests/integration/test_lightrag_graph.py`) fixa o comportamento esperado. Uma versão nova do LightRAG precisa passar nesse teste.
- As 58 dependências do extra `graph` têm licença permitida pelo ADR-0001.
- A primeira instalação do LightRAG fez o `tenacity` voltar de 9.2.1 para 9.1.4 no lock. A bateria de testes passou com a versão nova do lock.
