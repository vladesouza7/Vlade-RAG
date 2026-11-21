# Dataset legal-ptbr

Dataset de avaliação em português do Brasil com 100 documentos e 20 perguntas.

## Fonte

O dataset usa o texto original de duas leis federais, publicado no site da Câmara dos Deputados:

| Lei | Documentos | Prefixo |
|---|---|---|
| LGPD, Lei 13.709/2018 | 50 | `lgpd-` |
| Código de Defesa do Consumidor, Lei 8.078/1990 | 50 | `cdc-` |

O texto de lei não tem proteção de direito autoral no Brasil (Lei 9.610/1998, artigo 8º, inciso IV).

Atenção: os arquivos têm a publicação original, sem as alterações posteriores das leis. Não use este dataset como fonte jurídica.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `docs/*.md` | Um documento por grupo de artigos consecutivos, com o capítulo de origem |
| `manifest.json` | Lei e artigos de cada documento, e o endereço de origem |
| `questions.jsonl` | Pergunta, resposta esperada, documento relevante, lei e artigo |
| `questions-typos.jsonl` | As mesmas perguntas com letras trocadas em duas palavras longas de cada pergunta. Testa o retriever fuzzy |
| `questions-paraphrase.jsonl` | As mesmas perguntas com palavras do dia a dia, escritas à mão, sem os termos da lei. Testa a reescrita de consulta, o multi-query e o HyDE |

## Como gerar de novo

```bash
python3 scripts/datasets/build_legal_ptbr.py --cache /tmp/legal-cache
```

O script confere que a frase-chave de cada resposta existe no documento relevante. Se a frase não existe, o script para com erro.

## Variantes das perguntas

As 20 perguntas de `questions.jsonl` usam as palavras da lei. A busca por palavras exatas já acha o documento certo (Recall@10 de 1,00), então esse arquivo não mostra o ganho do fuzzy nem o da reescrita de consulta. Duas variantes mantêm o mesmo documento relevante e mudam só a pergunta:

- **`questions-typos.jsonl`:** o script troca duas letras vizinhas no meio das duas maiores palavras de cada pergunta (palavras com 7 letras ou mais). A regra é fixa, então o arquivo é igual a cada execução. A pergunta 2 não tem palavra com 7 letras e fica igual à original.
- **`questions-paraphrase.jsonl`:** uma pessoa escreveu cada paráfrase. A paráfrase pede a mesma informação da pergunta original, sem os termos da lei. O gabarito não muda.

Para gerar de novo:

```bash
python3 scripts/datasets/derive_legal_ptbr_variants.py
```

Atenção: as variantes herdam as limitações do gabarito original. Na pergunta 5 ("Quem é o encarregado..."), o `lgpd-026` (artigo 41) também responde, mas o gabarito lista só o `lgpd-003` (limitação L10 do roadmap).
