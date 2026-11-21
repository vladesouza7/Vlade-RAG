# ADR-0019: Transformadores de consulta e retriever fuzzy

- Status: Aceito
- Data: 2026-11-20
- Complementa o ADR-0005 (item 3) e o ADR-0018

## Contexto

O RF-25 pede transformação da consulta por configuração: reescrita, multi-query e HyDE. O RF-21 e o item 3 do ADR-0005 pedem o retriever fuzzy com `pg_trgm`. As duas técnicas têm um custo: a transformação chama o LLM a cada busca, e o fuzzy exige um índice GIN de trigramas.

O dataset `legal-ptbr` original usa as palavras da lei. Nele, a busca por palavras exatas já acha o documento certo (Recall@10 de 1,00). Para medir as duas técnicas, a tarefa criou duas variantes das 20 perguntas, com o mesmo gabarito:

- `questions-typos.jsonl`: duas letras trocadas em duas palavras longas de cada pergunta.
- `questions-paraphrase.jsonl`: palavras do dia a dia, escritas à mão, sem os termos da lei.

## Decisão

1. **Transformadores.** `LLMQueryTransformer` tem três modos: `rewrite`, `multi_query` e `hyde`. Ele usa o LLM da base (`generation.provider` e `generation.model`) e prompts versionados em pt-BR e em inglês.
2. **Fusão.** O `Search` roda cada consulta em cada retriever e funde todas as listas com RRF. A lista da consulta original usa o nome do retriever. As listas das consultas derivadas usam `dense#1`, `lexical#1` e assim por diante.
3. **A consulta original.** Ela sempre vem primeiro e sempre roda. O `Search` a recoloca na frente se um plugin a esquecer. O reranker usa a consulta original.
4. **HyDE.** O parágrafo hipotético vai só ao retriever denso (`Query.retrievers`). A forma léxica de um parágrafo inteiro casaria com quase todos os chunks.
5. **Falha do LLM.** Se o LLM falha ou não devolve texto útil, a busca continua com a consulta original e o log recebe um aviso com o `finish_reason`. Um erro de configuração do provedor (`InvalidArgument`) não é escondido.
6. **Limite de saída.** O transformador usa o `generation.max_output_tokens` da base. Um modelo com raciocínio gasta parte do limite pensando. Com um limite fixo de 512, o `tencent/hy4-flash` terminava sem resposta em parte das perguntas.
7. **Fuzzy.** `TrigramLexicalIndex` divide a pergunta em palavras, descarta as stop words (com `ts_lexize`) e compara cada palavra com as palavras do chunk por similaridade de trigramas (`word_similarity`, limiar 0,5). A pontuação do chunk é a soma da melhor similaridade de cada palavra. O backend `memory` tem um equivalente aproximado (`MemoryFuzzyIndex`).
8. **O índice trigram.** A migração `0002_trigram_index.sql` cria a função `vlade_ensure_trigram_index()`. O adapter chama a função na primeira busca fuzzy do processo, e a função cria o índice `chunks_trgm_idx`. Nenhuma base paga o índice antes disso. Sem a migração, o erro manda rodar `vlade-rag db upgrade`.
9. **Os valores padrão não mudam.** `query_transform` continua `none` e `retrievers` continua `[dense, lexical]`. A medida abaixo não justifica ligar nenhuma das duas técnicas por padrão.
10. **Medição.** `vlade-rag eval run` aceita `--retrievers` e `--query-transform`, que valem só para a execução e não mudam a base.
11. **Plugins.** Um plugin do tipo `query_transformer` recebe o resolvedor de LLM, o registro de prompts e o maior tamanho de consulta do servidor. O port `QueryTransformer.transform` recebe a base (`kb`).

## Medida de 2026-11-20

Base `legal-ptbr` (100 documentos, 20 perguntas por dataset), embeddings `openai/text-embedding-3-small`, geração `tencent/hy4-flash`. A coluna "reranker" usa `mongodb/rerank-2.5` com 50 candidatos. Nenhuma execução teve aviso de transformação. Os 30 relatórios estão em `evals/reports/fase3-consulta-fuzzy/`.

| Configuração | Original: Recall@10 | Original: MRR | Erros de digitação: Recall@10 | Erros de digitação: MRR | Paráfrases: Recall@10 | Paráfrases: MRR |
|---|---|---|---|---|---|---|
| Linha de base (denso e léxico) | 1,00 | 0,786 | 0,90 | 0,729 | 0,90 | 0,498 |
| com fuzzy | 1,00 | 0,841 | 0,90 | 0,754 | 0,85 | 0,485 |
| com `rewrite` | 0,95 | 0,756 | 1,00 | 0,756 | 0,95 | 0,596 |
| com `multi_query` | 0,95 | 0,744 | 0,95 | 0,769 | 0,95 | 0,622 |
| com `hyde` | 1,00 | 0,854 | 1,00 | 0,775 | 0,95 | 0,681 |
| com reranker | 1,00 | 0,975 | 1,00 | 0,975 | 0,95 | 0,950 |
| reranker e fuzzy | 1,00 | 0,975 | 1,00 | 0,975 | 0,95 | 0,950 |
| reranker e `rewrite` | 1,00 | 0,975 | 1,00 | 0,975 | 0,95 | 0,950 |
| reranker e `multi_query` | 1,00 | 0,975 | 1,00 | 0,975 | 0,95 | 0,950 |
| reranker e `hyde` | 1,00 | 0,975 | 1,00 | 0,975 | 0,95 | 0,950 |

Resultados:

- **Com o reranker, as duas técnicas não mudam nada.** As quatro combinações com reranker dão o mesmo resultado do reranker sozinho nos três datasets. O reranker já coloca o documento certo em primeiro lugar quando ele está entre os 50 candidatos.
- **Sem o reranker, o HyDE é a melhor transformação.** O MRR sobe de 0,786 para 0,854 no original, de 0,729 para 0,775 nos erros de digitação e de 0,498 para 0,681 nas paráfrases.
- **`rewrite` e `multi_query` ajudam só nas paráfrases** (MRR de 0,498 para 0,596 e 0,622). No dataset original, os dois pioram o Recall@10 (de 1,00 para 0,95) e o MRR. O `multi_query` pode piorar muito uma pergunta: "Quando a LGPD entra em vigor?" com erros de digitação passou da posição 1 para a posição 34.
- **O fuzzy ajuda pouco, até com erros de digitação.** No dataset de erros de digitação, o MRR sobe de 0,729 para 0,754 e o Recall@10 não muda. Em algumas perguntas ele piora: a pergunta 1 com erros passou da posição 1 para a posição 4. Nas paráfrases, o fuzzy baixa o Recall@10 (de 0,90 para 0,85). Ninguém investigou a causa.
- **Uma pergunta nenhuma configuração acha.** Nenhuma configuração acha o documento certo da paráfrase da pergunta 2 ("A partir de que data essa lei de proteção de dados começou a valer?"). Ele não aparece entre os 10 primeiros. Esse é o teto de Recall@10 de 0,95 nas paráfrases.

Limites da medida:

- Cada dataset tem 20 perguntas e um documento relevante por pergunta. Uma diferença de 0,05 em Recall@10 é uma pergunta.
- As variantes herdam o gabarito original, inclusive a limitação da pergunta 5 (L10 do roadmap).
- As paráfrases são de um autor só e são pequenas. O resultado dos transformadores nelas é um sinal, não uma prova.
- A latência e o custo dos transformadores não foram medidos. Cada busca com transformação faz uma chamada ao LLM da base. O `tencent/hy4-flash` gasta de 260 a 470 tokens raciocinando antes de responder. A tarefa 3.10 mede a latência.

## Alternativas avaliadas

- **Ligar o HyDE por padrão:** o HyDE é o melhor sem o reranker, mas custa uma chamada ao LLM por busca, e com o reranker ele não muda nada. Recusado.
- **O fuzzy com a pergunta inteira (`word_similarity` da frase):** uma pergunta em linguagem natural tem palavras longe umas das outras no chunk, e a similaridade da frase fica baixa. A comparação por palavra resolve isso.
- **Um limite de saída próprio do transformador:** falhou com modelos que raciocinam. Recusado.
- **Criar o índice trigram na migração inicial:** toda base pagaria o espaço e a lentidão de escrita. Recusado.
- **Descartar a consulta original quando há uma reescrita:** a reescrita piora o dataset original. Manter a original protege a recuperação.

## Consequências

- Quem atualiza uma instalação existente roda `vlade-rag db upgrade` para aplicar a migração 0002 antes de ligar o fuzzy.
- A criação do índice trigram bloqueia escritas na tabela `chunks` enquanto ela roda. Em uma tabela grande, rode a primeira busca fuzzy fora do horário de pico.
- O limiar de 0,5 do fuzzy é fixo no código.
- A fase 3 segue com o reranker como a melhoria de recuperação comprovada. As duas técnicas ficam disponíveis por configuração, para quem não pode usar um reranker.
