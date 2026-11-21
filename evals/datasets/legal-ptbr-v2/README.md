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

## Primeiras medidas

Embeddings `openai/text-embedding-3-small`, busca densa e léxica com RRF, reranker `mongodb/rerank-2.5` com 50 candidatos. Os relatórios estão em [`evals/reports/fase3-dataset-v2/`](../../reports/fase3-dataset-v2/).

| Configuração | Perguntas | MRR | Recall@1 | Recall@10 | MRR formais | MRR coloquiais |
|---|---|---|---|---|---|---|
| Linha de base | originais | 0,740 | 0,56 | 0,98 | 0,781 | 0,653 |
| com fuzzy | originais | 0,783 | 0,61 | 0,98 | 0,850 | 0,642 |
| com reranker | originais | 0,959 | 0,87 | 1,00 | 0,980 | 0,914 |
| com reranker e fuzzy | originais | 0,959 | 0,87 | 1,00 | 0,980 | 0,914 |
| Linha de base | erros de digitação | 0,679 | 0,50 | 0,91 | 0,745 | 0,538 |
| com reranker | erros de digitação | 0,953 | 0,87 | 0,99 | 0,980 | 0,895 |

- **O reranker não satura.** No `legal-ptbr` os cinco rerankers chegavam a MRR 0,975 e Recall@1 de 0,95. Aqui o reranker fica em MRR 0,959 e Recall@1 de 0,87, e sobra espaço para uma técnica melhorar.
- **A folga está nas perguntas coloquiais.** Com o reranker, as perguntas formais têm MRR 0,980 e as coloquiais têm 0,914.
- **O Marco Civil é o grupo mais difícil sem reranker.** O grupo `mci` tem MRR 0,609 e Recall@10 de 0,89, contra Recall@10 de 1,00 em `cdc`, `lgpd` e `lai`.
- **O fuzzy ajuda as perguntas formais e não ajuda as coloquiais.** Sem reranker, o MRR das formais sobe de 0,781 para 0,850, e o das coloquiais cai de 0,653 para 0,642. Nas perguntas `multi`, o Recall@10 cai de 0,97 para 0,87.
- **Com o reranker, o fuzzy não muda as métricas.** A posição do primeiro documento relevante é a mesma nas 109 perguntas. A ordem dos 10 primeiros documentos muda em 47 delas.

Estas medidas estão incompletas. A chave do OpenRouter atingiu o limite de gasto antes de rodarem a reescrita, o multi-query, o HyDE e os rerankers `cohere/rerank-4-fast` e `qwen/qwen3-reranker-8b`. O modelo gratuito `nvidia/nemotron-3.5-rerank-8b:free` não completa a avaliação: o OpenRouter limita os modelos gratuitos a 20 requisições por minuto, e a avaliação faz uma requisição por pergunta.

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
