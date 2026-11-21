# Benchmark da fase 3 (tarefa 3.10)

Este relatório mede o RNF-01 a RNF-04 do `PROJECT_SPEC.md`. O ADR-0020 propõe o que fazer com as metas que falham.

**Resumo.** Nenhuma meta de latência de busca foi cumprida nesta máquina. Na base pequena, a causa principal é o embedding remoto. Nas bases maiores, é a busca lexical.

| RNF | Meta | Medida | Resultado |
|---|---|---|---|
| 01 | p95 de `search` sem reranker, base de 1 milhão de chunks, ≤ 300 ms | Base pequena (184 chunks): p95 de 812 ms. Base sintética: p95 de 408 ms com 6 mil chunks e 7,998 s com 104 mil | **Não cumprido.** A base de 1 milhão não coube na máquina |
| 02 | p95 de `search` com reranker de 50 candidatos, ≤ 1 s | p95 de 1,978 s (`mongodb/rerank-2.5`) e 2,229 s (`cohere/rerank-4-fast`) | **Não cumprido** |
| 03 | Tempo até o primeiro token, sem o LLM remoto, ≤ 1,5 s | Base de 104 mil chunks: p95 de 591 ms só com a busca vetorial, e 7,559 s com a configuração padrão | Cumprido só com a busca vetorial |
| 04 | Vazão de ingestão por worker, sem embeddings, ≥ 50 páginas por segundo | De 8 a 70 páginas por segundo, conforme o tamanho do documento | Cumprido só para documentos longos |

O que explica os números:

- **O embedding remoto da pergunta domina a busca.** Na base pequena, de cada 812 ms de p95, 787 ms são a chamada ao provedor de embeddings. A busca no banco leva de 13 a 21 ms.
- **O reranker por API passa de 1 s sozinho.** O p95 só do reranker é de 1,216 s e de 1,435 s.
- **A busca lexical cresce com o tamanho da base.** O p95 dela sobe de 401 ms (6 mil chunks) para 7,939 s (104 mil chunks). A busca vetorial não cresce do mesmo jeito, mas o p95 dela saltou no maior estágio, junto com o uso de memória.
- **A ingestão paga um custo fixo por documento.** Cada documento custa 62 transações no PostgreSQL. Um documento curto não diluí esse custo.

## Ambiente

| Item | Valor |
|---|---|
| Máquina | 4 CPUs, 7,7 GB de RAM, WSL2 no Windows |
| PostgreSQL | 17.12 em container Docker, com limite de **1 GiB** de memória |
| Python | 3.12.3 |
| Motor Rust | **Não instalado.** A normalização, o chunking e o hash rodaram na reserva em Python |
| Provedores | OpenRouter: embeddings `openai/text-embedding-3-small`, rerankers por API |
| Caches | Desligados. Toda consulta é fria |

## Método

O script é `scripts/benchmarks/bench.py`. Ele roda a biblioteca em processo, sem HTTP, contra o PostgreSQL e os provedores das variáveis `VLADE_*`. A especificação cita o `k6`. Este benchmark não usa o `k6`, então ele não mede a camada HTTP.

- **Percentis:** posto mais próximo (*nearest rank*) sobre as consultas medidas. Cada medida tem 100 consultas, depois de 3 de aquecimento.
- **Etapas:** um *tracer* registra o tempo de cada etapa da consulta: embedding, busca vetorial, busca lexical, fusão e reranker.
- **Falhas:** uma consulta que falha entra na contagem de falhas e não entra na latência. Os relatórios desta pasta têm 0 falhas.
- **Consultas:** as 100 primeiras perguntas de `evals/datasets/legal-ptbr-v2/questions.jsonl`.
- **Página:** 3.000 caracteres, cerca de 500 palavras.
- **Ingestão (RNF-04):** o provedor de embeddings é o `hashing`, local. O script mede o tempo dentro dele para subtrair. A medida roda um worker, com o número de jobs ao mesmo tempo indicado em cada tabela. O padrão do worker é 2.

## RNF-04: ingestão

A vazão depende do tamanho do documento. Cada documento paga um custo fixo de **62 transações** no PostgreSQL, medido pela diferença de `xact_commit` do banco, igual nas quatro medidas. Duas medidas permitem estimar o tempo de um documento em cerca de 0,16 s fixos mais 15 a 18 ms por página.

Páginas por segundo, sem o tempo de embeddings, pelo tamanho do documento:

| Páginas por documento | 1 job | 2 jobs (padrão do worker) |
|---|---|---|
| 1 | 8,3 | 14,6 |
| 3 | 15,1 | 29,2 |
| 10 | 25,9 | 51,2 |
| 30 | 38,8 | 43,0 |
| 100 | 56,0 | 70,0 |

Documentos curtos do dataset (cerca de 0,45 página, 300 documentos), páginas por segundo no total:

| Jobs ao mesmo tempo | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| Páginas por segundo | 2,6 | 4,2 | 5,2 | 6,4 |

O que a medida mostra:

- **A meta de 50 páginas por segundo vale para documentos de cerca de 100 páginas.** Com 2 jobs, o ponto de 10 páginas também passa (51,2), por pouco.
- **Documentos curtos ficam muito abaixo.** Com 1 página por documento, a vazão é de 8 a 15 páginas por segundo.
- **O gargalo é o banco, não o motor.** Um perfil de 150 documentos curtos mostrou 72% do tempo de relógio (20 de 28 s) parado esperando I/O de rede, que neste processo é o PostgreSQL. A reserva em Python do motor nativo custou 1,9% do tempo de processamento.
- **A vazão se manteve com o índice grande.** A ingestão de documentos de 100 páginas, com 2 jobs, ficou entre 58 e 94 páginas por segundo no total. Isso vale para os cinco estágios do teste de escala, até 104 mil chunks.
- **Cada ponto é uma execução com poucos documentos.** O ponto de 30 páginas com 2 jobs (43,0) destoa por ter só 5 documentos. Trate a diferença entre pontos vizinhos como ruído.

## RNF-01 e RNF-02: busca na base real

Base `legal-ptbr-v2`: 150 documentos, 184 chunks. O embedding da pergunta é remoto. Latência em milissegundos, 100 consultas, uma de cada vez:

| Configuração | p50 | p95 | p99 | Embedding (p95) | Vetorial (p95) | Lexical (p95) | Reranker (p95) |
|---|---|---|---|---|---|---|---|
| Sem reranker | 707 | 812 | 1.052 | 787 | 13 | 21 | — |
| `mongodb/rerank-2.5` | 1.752 | 1.978 | 2.285 | 723 | 19 | 25 | 1.216 |
| `cohere/rerank-4-fast` | 1.977 | 2.229 | 2.586 | 863 | 15 | 29 | 1.435 |

As etapas são medidas em separado. A soma dos p95 de cada etapa não é o p95 total.

O reranker `qwen/qwen3-reranker-8b` não tem medida: só 11 de 100 consultas funcionaram, e o relatório incompleto não está nesta pasta.

## RNF-01: escala

A base `bench-hash` é sintética. O script a cresceu com documentos de 100 páginas copiados do dataset, com embeddings `hashing` de 1.024 dimensões. Não há chamada a provedor: o número é só do PostgreSQL. A busca usa os retrievers `dense` e `lexical`.

Latência em milissegundos, 100 consultas, uma de cada vez:

| Chunks | Memória do PostgreSQL | p50 | p95 | Vetorial (p95) | Lexical (p95) |
|---|---|---|---|---|---|
| 6.143 | 20% | 232 | 408 | 16 | 401 |
| 11.066 | 26% | 368 | 677 | 15 | 670 |
| 15.956 | 42% | 578 | 1.183 | 78 | 1.174 |
| 35.543 | 67% | 941 | 1.544 | 32 | 1.526 |
| 64.943 | 71% | 2.148 | 4.125 | 267 | 4.029 |
| 104.156 | 87% | 5.759 | 7.998 | 3.199 | 7.939 |

Com 4 consultas ao mesmo tempo, a vazão sobe de 0,19 para 0,47 consulta por segundo no último estágio, e a latência piora (p95 de 12,6 s).

O que a medida mostra:

- **A busca lexical cresce quase em linha reta.** Ela custa de 43 a 76 µs de p95 por chunk, em todos os tamanhos. O índice junta os termos da pergunta com OU e classifica (`ts_rank_cd`) todos os chunks que casam, não só os 50 melhores.
- **A busca vetorial fica abaixo de 270 ms até 65 mil chunks.** No último estágio, com 104 mil chunks, ela salta para 3,199 s no p95.
- **O salto coincide com dois fatos, e a causa não foi investigada.** O PostgreSQL estava em 87% do limite de 1 GiB do container, e a busca lexical rodava ao mesmo tempo, em paralelo com a vetorial. Na mesma base, com a busca vetorial rodando sozinha (teste do primeiro token), o p95 foi de 579 ms. Ninguém mediu o acerto de cache nem a leitura de disco.
- **A base de 1 milhão de chunks não cabe nesta máquina.** Só os vetores de 1.024 dimensões de 1 milhão de chunks ocupam cerca de 4 GB, mais que o limite de 1 GiB do container.

## RNF-03: tempo até o primeiro token

A medida usa um LLM que responde na hora, com embeddings `hashing` locais. Ela deixa de fora o LLM remoto e o embedding remoto. Base `bench-hash` com 104.156 chunks, 30 consultas:

| Retrievers | p50 | p95 | p99 |
|---|---|---|---|
| Só `dense` | 527 ms | 591 ms | 931 ms |
| `dense` e `lexical` (padrão) | 4.388 ms | 7.559 ms | 7.778 ms |

O primeiro token sai logo depois da busca. O tempo até o primeiro token é o tempo da busca mais a montagem do contexto.

O mesmo teste com a base real e o provedor de embeddings remoto não rodou: o limite de gasto da chave do OpenRouter acabou. Um teste de fumaça com 5 consultas deu p50 de 731 ms, com 714 ms de embedding no p95. Cinco consultas não são uma medida.

## O que não foi medido

O limite total de gasto da chave do OpenRouter acabou durante a medição. Ficaram sem medida:

- as transformações de consulta com LLM (HyDE, reescrita e multi-query). A limitação L13 do roadmap continua aberta.
- o reranker `qwen/qwen3-reranker-8b`.
- a vazão da busca com 4 consultas ao mesmo tempo contra o provedor real.
- o tempo até o primeiro token com a base real e com reranker.
- o reranker local (`bge-reranker-v2-m3`). A máquina de desenvolvimento não roda modelos locais.
- o RNF-01 com 1 milhão de chunks.

## Limitações da medida

- **Uma só máquina, sem isolamento.** O notebook também roda o Docker e o Windows. A variação entre execuções pode ser grande. O p95 da busca vetorial a 104 mil chunks foi de 3,199 s com a busca lexical rodando junto e de 579 ms com ela sozinha. As duas execuções diferem em mais de um fator, então a medida não separa a causa.
- **A base sintética repete 150 documentos.** Todo termo da pergunta casa com uma fração enorme dos chunks. Um corpus real, com vocabulário mais variado, casa menos. O resultado da busca lexical é um alerta de escala, não uma previsão.
- **Os embeddings `hashing` não têm a geometria de embeddings reais.** O custo da busca vetorial com vetores reais pode ser diferente.
- **Uma só configuração do PostgreSQL.** Valores padrão, container de 1 GiB. Um ajuste de memória (`shared_buffers`, `maintenance_work_mem`) não foi testado.
- **Sem camada HTTP.** O benchmark chama a biblioteca. A API REST e o servidor MCP acrescentam tempo que não está aqui.
- **Sem o motor Rust.** O motor nativo não rodou. No perfil de documentos curtos, o banco domina, e a reserva em Python pesa pouco. Os documentos longos não foram perfilados, e o motor Rust pode elevar a vazão deles.

## Como repetir

Use uma chave de administrador (`VLADE_API_KEY`) e as variáveis `VLADE_*` da CLI. Rode com `uv run python`:

```bash
# Ingestão: documentos de 100 páginas, 2 jobs ao mesmo tempo
python scripts/benchmarks/bench.py ingest --kb bench-hash \
  --docs evals/datasets/legal-ptbr-v2/docs --replicas 5 --pages-per-document 100 --concurrency 2

# Busca na base real, sem reranker e com reranker
python scripts/benchmarks/bench.py search --kb legal-ptbr-v2 \
  --dataset evals/datasets/legal-ptbr-v2/questions.jsonl --n 100
python scripts/benchmarks/bench.py search --kb legal-ptbr-v2 \
  --dataset evals/datasets/legal-ptbr-v2/questions.jsonl --n 100 --rerank-model mongodb/rerank-2.5

# Tempo até o primeiro token, sem o LLM remoto
python scripts/benchmarks/bench.py ttft --kb bench-hash \
  --dataset evals/datasets/legal-ptbr-v2/questions.jsonl --n 30 --retrievers dense
```

A base `bench-hash` usa embeddings `hashing`. Para crescer a base, repita o comando `ingest` com `--start-replica` diferente a cada vez. Apague a base de teste quando acabar: com 104 mil chunks ela ocupa cerca de 1,8 GB no banco.
