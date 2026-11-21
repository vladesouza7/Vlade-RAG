# ADR-0018: Reranker por API primeiro, reranker local como extra opcional

- Status: Aceito
- Data: 2026-11-20
- Complementa o item 2 do ADR-0008

## Contexto

O item 2 do ADR-0008 define o `BAAI/bge-reranker-v2-m3` pelo adapter `sentence-transformers` como reranker padrão. Esse adapter instala o PyTorch. O PyTorch pesa centenas de megabytes e, nas distribuições com CUDA, traz bibliotecas NVIDIA com licença própria. O notebook de desenvolvimento tem 8 GB de memória e não comporta o modelo junto com os outros serviços.

A fase 3 precisa medir o ganho do reranker contra a linha de base da fase 1. A medida precisa rodar agora, na máquina de desenvolvimento. Um reranker falso não prova ganho.

O OpenRouter publica o endpoint `POST /rerank`. O formato é o da Cohere: a requisição leva `model`, `query`, `documents` e `top_n`. A resposta traz `results[].index` e `results[].relevance_score`, mais `usage.cost`. O projeto já usa o OpenRouter para LLM e embeddings, com a mesma chave `OPENROUTER_API_KEY`.

## Decisão

1. O primeiro adapter do port `Reranker` chama um endpoint `/rerank` no formato Cohere. A classe é `ApiReranker`, em `vlade_rag.reranking.api`. Ela não tem dependência nova.
2. O adapter fica registrado como plugin `reranker` para o OpenRouter e para cada provedor que o operador acrescenta em `VLADE_PROVIDERS__COMPATIBLE__<NOME>__*`. Os provedores `openai`, `opencode` e `gemini` não têm endpoint de rerank e não recebem o plugin.
3. O modelo é configuração: `retrieval.rerank.provider: openrouter` e `retrieval.rerank.model: <modelo>`. Trocar de modelo não muda código.
4. O adapter local com `sentence-transformers` e `bge-reranker-v2-m3` continua previsto. Ele entra como extra opcional (`local-models`), fora das dependências base, em outra tarefa. Quem processa dados que não podem sair da infraestrutura usa o adapter local.
5. O padrão de `RerankConfig` continua `enabled: false`. O valor `provider: sentence-transformers` do padrão ainda não tem adapter. Quem liga o reranker agora escolhe `provider: openrouter` e um modelo.
6. `vlade-rag eval run` aceita `--rerank-model` e `--rerank-provider`. As opções valem só para a execução e não mudam a base. Com o reranker ligado, o avaliador eleva `top_n` ao número de trechos buscados. Um `top_n` de 8 cortaria o ranking e reduziria o Recall@10 por um motivo que não é a qualidade do reranker. O relatório grava o valor usado.

## Privacidade

O adapter por API envia o texto de cada candidato ao provedor. Para dados privados de um tenant, o operador decide se aceita esse envio. Os modelos gratuitos podem registrar as requisições. Use esses modelos só com dados públicos, como o dataset `legal-ptbr`.

## Medida de 2026-11-20

Base `legal-ptbr`: 100 documentos, 20 perguntas, busca densa e léxica com RRF, 50 candidatos para o reranker. Os relatórios estão em `evals/reports/`.

| Configuração | Recall@1 | MRR | NDCG@10 | Custo por requisição (50 documentos) | Latência mediana |
|---|---|---|---|---|---|
| Linha de base, sem reranker | 0,70 | 0,786 | 0,838 | — | — |
| `cohere/rerank-v3.5` | 0,95 | 0,975 | 0,982 | US$ 0,002 | 1,5 s |
| `cohere/rerank-4-fast` | 0,95 | 0,975 | 0,982 | US$ 0,002 | 1,1 s |
| `mongodb/rerank-2.5` (Voyage) | 0,95 | 0,975 | 0,982 | US$ 0,00087 | 0,9 s |
| `qwen/qwen3-reranker-8b` | 0,95 | 0,975 | 0,982 | US$ 0,0042 | 1,4 s |
| `nvidia/nemotron-3.5-rerank-8b:free` | 0,95 | 0,975 | 0,982 | US$ 0 | 1,3 s |

Resultados:

- Os cinco modelos dão as mesmas métricas. O Recall@10 já era 1,00 na linha de base e continua 1,00.
- A pergunta 20 (limitação L1) passou da posição 9 para a posição 1 nos cinco modelos.
- A pergunta 5 passou da posição 1 para a posição 2 nos cinco modelos. Os modelos põem o `lgpd-026` (artigo 41, a seção sobre o encarregado) antes do `lgpd-003` (artigo 5, a definição). O `lgpd-026` também responde à pergunta, mas o dataset só lista o `lgpd-003`. O gabarito não muda, para manter a comparação com a linha de base.
- A ordem dos 10 primeiros documentos muda em todas as 20 perguntas entre os modelos. As métricas coincidem porque o dataset tem um documento relevante por pergunta e o primeiro documento relevante está na mesma posição em todos.

Limites da medida:

- O dataset de 20 perguntas não separa os cinco modelos. A escolha entre eles espera um dataset maior ou com mais de um documento relevante por pergunta.
- Cada medida de custo e de latência vem de 3 requisições com 50 documentos de até 2000 caracteres. A latência inclui a rede. Não é o benchmark da tarefa 3.10.
- A requisição leva de 0,9 s a 1,5 s sozinha. O RNF-02 pede p95 de 1 s para a busca com 50 candidatos. O benchmark da tarefa 3.10 decide se o RNF-02 se cumpre com o reranker por API.
- Ninguém verificou ainda as licenças e os termos de uso dos cinco modelos (item 4 do ADR-0008). O adapter não distribui modelos.

## Alternativas avaliadas

- **Só o `sentence-transformers`:** é o padrão do ADR-0008, mas não roda no notebook de desenvolvimento. A fase 3 ficaria sem medida real.
- **Um reranker falso nos testes e a medida real em outra máquina:** o teste de contrato roda, mas a fase 3 não prova o ganho.
- **Um adapter para cada provedor (Cohere, Jina, Voyage):** o formato é o mesmo. Um adapter com um endpoint configurável cobre os três.
- **Reranker por LLM (um prompt que pontua cada candidato):** custa mais por consulta, tem latência maior e a pontuação varia entre execuções.

## Consequências

- A tarefa 3.1 do roadmap fica parcial até o adapter local existir.
- O `ARCHITECTURE.md` descreve `provider: openrouter` como valor aceito de `retrieval.rerank.provider`.
- O ADR-0008 mantém o `bge-reranker-v2-m3` como padrão do adapter local.
- A fase 3 acrescenta um dataset maior antes de escolher o modelo padrão de reranking.

## Atualização de 2026-11-21: três rerankers no `legal-ptbr-v2`

No dataset `evals/datasets/legal-ptbr-v2` (109 perguntas), os rerankers de API se separam, o que o `legal-ptbr` não mostrava:

| Reranker | MRR | Recall@1 | Recall@10 | MRR coloquiais |
|---|---|---|---|---|
| `cohere/rerank-4-fast` | 0,940 | 0,85 | 1,00 | 0,881 |
| `mongodb/rerank-2.5` | 0,959 | 0,87 | 1,00 | 0,914 |
| `qwen/qwen3-reranker-8b` | 0,965 | 0,88 | 1,00 | 0,938 |

A diferença entre o melhor e o pior é de 0,025 de MRR, e o melhor muda de um grupo de perguntas para outro. Cada grupo tem de 10 a 20 perguntas. A escolha do modelo padrão continua aberta. Nas medidas do ADR, o `qwen/qwen3-reranker-8b` custou US$ 0,0042 por requisição de 50 documentos, contra US$ 0,00087 do `mongodb/rerank-2.5`. O `cohere/rerank-v3.5` e o `nvidia/nemotron-3.5-rerank-8b:free` não entraram nesta medida. O modelo gratuito não completa a avaliação, porque o OpenRouter limita os modelos gratuitos a 20 requisições por minuto.
