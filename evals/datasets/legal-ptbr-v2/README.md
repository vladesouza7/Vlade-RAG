# Dataset legal-ptbr-v2

Dataset de avaliação em português do Brasil com 150 documentos e 109 perguntas. O `legal-ptbr-v2` inclui o [`legal-ptbr`](../legal-ptbr/README.md) e acrescenta o que ele não tem.

## Por que existe

O `legal-ptbr` tem 20 perguntas e um documento relevante por pergunta. Um reranker leva as métricas dele ao teto. Os cinco modelos de reranking testados na fase 3 deram o mesmo resultado. O fuzzy, a reescrita de consulta, o multi-query e o HyDE não mudaram nada com o reranker ligado (limitação L10 do roadmap). Um dataset assim não escolhe entre duas configurações.

O `legal-ptbr-v2` muda isto de quatro formas:

- **Mais documentos, com palavras parecidas.** Duas leis novas falam de dados pessoais, consentimento, registros e sigilo, como a LGPD e o CDC. Elas criam documentos errados difíceis.
- **Mais perguntas.** São 109 perguntas, contra 20.
- **Dois estilos.** A pergunta formal usa as palavras da lei. A pergunta coloquial é do jeito que uma pessoa pergunta, na primeira pessoa e sem os termos da lei.
- **Perguntas com mais de um documento relevante.** Treze perguntas têm dois ou mais documentos relevantes.

## Fonte

O dataset usa o texto original de quatro leis federais, publicado no site da Câmara dos Deputados:

| Lei | Documentos | Prefixo |
|---|---|---|
| LGPD, Lei 13.709/2018 | 50 | `lgpd-` |
| Código de Defesa do Consumidor, Lei 8.078/1990 | 50 | `cdc-` |
| Marco Civil da Internet, Lei 12.965/2014 | 25 | `mci-` |
| Lei de Acesso à Informação, Lei 12.527/2011 | 25 | `lai-` |

O texto de lei não tem proteção de direito autoral no Brasil (Lei 9.610/1998, artigo 8º, inciso IV).

Atenção: os arquivos têm a publicação original, sem as alterações posteriores das leis. Não use este dataset como fonte jurídica. O artigo 44 da LAI não tem documento próprio: o texto dele fica no fim do artigo 43.

Os documentos de LGPD e de CDC são os mesmos do `legal-ptbr` (mesmos nomes, mesmo texto). O gerador confere isso.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `docs/*.md` | Um documento por grupo de artigos consecutivos, com o capítulo de origem |
| `manifest.json` | Lei e artigos de cada documento, e o endereço de origem |
| `questions.jsonl` | As 109 perguntas, com resposta esperada, documentos relevantes, grupo, estilo e evidências |
| `questions-typos.jsonl` | As mesmas perguntas com duas letras trocadas em duas palavras longas. O gabarito é o mesmo |

## Grupos de perguntas

| Grupo | Perguntas | O que mede |
|---|---|---|
| `v1` | 20 | As perguntas do `legal-ptbr`, na mesma ordem. Permitem comparar com a linha de base da fase 1 |
| `lgpd` | 15 | Perguntas sobre um artigo da LGPD, que não estão no `v1` |
| `cdc` | 15 | Perguntas sobre um artigo do CDC |
| `mci` | 19 | Perguntas sobre o Marco Civil da Internet |
| `lai` | 20 | Perguntas sobre a Lei de Acesso à Informação |
| `multi` | 10 | A resposta precisa de dois artigos que ficam em documentos diferentes, às vezes de duas leis |
| `cross` | 10 | Uma definição ou lista que outras leis do dataset também têm, com palavras parecidas. A pergunta cita a lei |

Cada pergunta tem o campo `style` (`formal` ou `colloquial`). Há 74 perguntas formais e 35 coloquiais.

## Como o gabarito é feito

Cada pergunta nova traz uma ou mais **evidências**: a lei, o artigo e uma frase que o artigo contém. Os documentos relevantes da pergunta são os documentos que guardam esses artigos. O gerador para com erro se uma frase não está no texto do artigo.

O critério para um documento entrar no gabarito: **o documento contém a informação que a resposta esperada afirma**. Falar do mesmo assunto não basta.

### Auditoria do gabarito

Depois da primeira medição, as perguntas em que a maioria dos rerankers discordava do gabarito foram lidas uma a uma. Quatro receberam um documento relevante a mais, porque o texto dele contém a informação pedida:

| Pergunta | Documento acrescentado | Motivo |
|---|---|---|
| A oficina pode usar peça usada ou paralela no conserto do meu aparelho? | `cdc-026` | O artigo 70 do CDC trata de empregar na reparação peça ou componente de reposição usado, sem autorização do consumidor |
| Quando eu parar de usar um aplicativo, posso pedir que apaguem meus dados de lá? | `lgpd-045` | O artigo 60 da LGPD reescreve o artigo 7º, inciso X do Marco Civil com a mesma frase |
| O que acontece com o servidor público que se recusa a me dar uma informação? | `lai-004` | O artigo 7º, § 4º da LAI sujeita a medidas disciplinares o responsável pela negativa sem fundamento |
| Como a LGPD e a Lei de Acesso à Informação tratam o consentimento para dados pessoais? | `lgpd-004` | O artigo 8 da LGPD diz como o consentimento deve ser dado |

Cinco discordâncias ficaram como estavam. O documento que os rerankers preferem não contém a informação da resposta:

| Pergunta | Documento preferido | Por que não entra |
|---|---|---|
| Quem é o encarregado pelo tratamento de dados pessoais? (do `v1`) | `lgpd-026` (artigo 41) | O artigo 41 diz que o controlador indica o encarregado e lista as atividades dele. Só o artigo 5 define quem ele é |
| Preciso pagar para pedir à empresa acesso aos meus dados pessoais? | `lgpd-010` | Não menciona custo |
| Recebi em casa um produto que eu não pedi. Preciso pagar por ele? | `cdc-017` | Trata do arrependimento, da garantia contratual e das cláusulas nulas, não do produto enviado sem pedido |
| A operadora que me vende a internet pode guardar quais sites eu acesso? | `mci-008`, `mci-009` | Tratam dos provedores de aplicações, não do provedor de conexão |
| O que significa eliminação de dados segundo a LGPD? | `lgpd-008` | Diz que os dados são eliminados, mas não define o termo |

## Medidas

Embeddings `openai/text-embedding-3-small`, busca densa e léxica com RRF. Os rerankers usam 50 candidatos. As transformações de consulta usam o `tencent/hy4-flash`, o modelo de geração da base. Os 15 relatórios estão em [`evals/reports/fase3-dataset-v2/`](../../reports/fase3-dataset-v2/).

Perguntas de `questions.jsonl`:

| Configuração | MRR | Recall@1 | Recall@10 | MRR formais | MRR coloquiais |
|---|---|---|---|---|---|
| Linha de base | 0,740 | 0,56 | 0,98 | 0,781 | 0,653 |
| com fuzzy | 0,783 | 0,61 | 0,98 | 0,850 | 0,642 |
| com HyDE | 0,788 | 0,61 | 0,96 | 0,808 | 0,746 |
| com reescrita | 0,764 | 0,61 | 0,96 | 0,798 | 0,691 |
| com multi-query | 0,691 | 0,50 | 0,96 | 0,717 | 0,636 |
| reranker `cohere/rerank-4-fast` | 0,940 | 0,85 | 1,00 | 0,968 | 0,881 |
| reranker `mongodb/rerank-2.5` | 0,959 | 0,87 | 1,00 | 0,980 | 0,914 |
| reranker `qwen/qwen3-reranker-8b` | 0,965 | 0,88 | 1,00 | 0,977 | 0,938 |
| `mongodb` com fuzzy, HyDE, reescrita ou multi-query | 0,959 | 0,87 | 1,00 | 0,980 | 0,914 |

Perguntas de `questions-typos.jsonl` (erros de digitação):

| Configuração | MRR | Recall@1 | Recall@10 | MRR formais | MRR coloquiais |
|---|---|---|---|---|---|
| Linha de base | 0,679 | 0,50 | 0,91 | 0,745 | 0,538 |
| com fuzzy | 0,724 | 0,57 | 0,92 | 0,808 | 0,547 |
| reranker `mongodb/rerank-2.5` | 0,953 | 0,87 | 0,99 | 0,980 | 0,895 |

O que as medidas mostram:

- **O reranker não satura.** No `legal-ptbr` os cinco rerankers chegavam a MRR 0,975 e Recall@1 de 0,95. Aqui o melhor fica em MRR 0,965 e Recall@1 de 0,88, e sobra espaço para uma técnica melhorar.
- **A folga está nas perguntas coloquiais.** Com o reranker, as formais têm MRR de 0,968 a 0,980 e as coloquiais têm de 0,881 a 0,938.
- **Sem reranker, o HyDE e o fuzzy ajudam, cada um em um tipo de pergunta.** O HyDE sobe as perguntas coloquiais (MRR de 0,653 para 0,746) e o fuzzy sobe as formais (de 0,781 para 0,850). O fuzzy não ajuda as coloquiais (0,642).
- **A reescrita e o HyDE trocam recall por precisão no topo.** O MRR sobe, e o Recall@10 cai de 0,98 para 0,96.
- **O multi-query piora a busca.** O MRR cai de 0,740 para 0,691. A queda é maior no CDC (de 0,78 para 0,61) e no Marco Civil (de 0,61 para 0,48).
- **Com o reranker, as quatro técnicas não mudam as métricas.** A posição do primeiro documento relevante é a mesma nas 109 perguntas, com cada técnica. A ordem dos 10 primeiros muda em 27 a 47 perguntas.
- **Os três rerankers ficam próximos.** O MRR vai de 0,940 a 0,965, uma diferença de 0,025. O melhor reranker muda de um grupo para outro, e cada grupo tem de 10 a 20 perguntas. Esta medida não escolhe o modelo padrão.
- **Erros de digitação custam pouco com o reranker.** O MRR vai de 0,959 para 0,953.

Detalhes das execuções:

- Uma pergunta da execução com reescrita (sem reranker) não foi reescrita. O modelo gastou os 4000 tokens de saída raciocinando e terminou sem texto (`finish_reason=length`). A busca usou a consulta original. As outras execuções não tiveram aviso de transformação.
- O modelo gratuito `nvidia/nemotron-3.5-rerank-8b:free` não completa a avaliação. O OpenRouter limita os modelos gratuitos a 20 requisições por minuto, e a avaliação faz uma requisição por pergunta.
- A latência e o custo de cada técnica não foram medidos. Cada busca com HyDE, reescrita ou multi-query faz pelo menos uma chamada ao LLM.

## Limitações

- A auditoria leu só as perguntas em que dois dos três rerankers testados discordavam do gabarito. Um documento que também responde e que nenhum reranker preferiu passa sem ser visto.
- As perguntas novas e as paráfrases do `v1` têm um autor só. Uma pergunta escrita para o dataset tem o jeito de quem a escreveu.
- Nas perguntas `multi`, o Recall@1 não passa de 0,5 por construção: uma pergunta com dois documentos relevantes não tem os dois na primeira posição. Leia essas perguntas pelo Recall@10.
- O dataset mede a recuperação por documento. Não há pergunta sem resposta nas fontes, que mediria a recusa do sistema.
- Cada grupo tem de 10 a 20 perguntas. Uma diferença de uma pergunta muda o resultado do grupo em 5% a 10%.

## Como gerar de novo

```bash
python3 scripts/datasets/build_legal_ptbr_v2.py --cache /tmp/legal-cache
```

O gerador baixa as quatro leis, monta os 150 documentos, confere que os documentos de LGPD e de CDC são iguais aos do `legal-ptbr` e confere cada evidência. As perguntas novas estão em `scripts/datasets/legal_ptbr_v2_questions.py`.

## Como medir

Ingerir os documentos e rodar a avaliação:

```bash
vlade-rag kb create legal-ptbr-v2 --config kb.json
vlade-rag ingest legal-ptbr-v2 evals/datasets/legal-ptbr-v2/docs --wait
vlade-rag eval run legal-ptbr-v2 --dataset evals/datasets/legal-ptbr-v2/questions.jsonl \
  --k 10 --output relatorio.json
```

Resumir um relatório por grupo e por estilo:

```bash
python3 scripts/datasets/summarize_by_group.py \
  evals/datasets/legal-ptbr-v2/questions.jsonl relatorio.json
```
