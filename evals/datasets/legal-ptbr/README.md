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

## Como gerar de novo

```bash
python3 scripts/datasets/build_legal_ptbr.py --cache /tmp/legal-cache
```

O script confere que a frase-chave de cada resposta existe no documento relevante. Se a frase não existe, o script para com erro.
