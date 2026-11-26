# ADR-0033: OKF v0.2 e LLM-Wiki

- Status: Aceito
- Data: 2026-11-25

## Contexto

A busca híbrida e o grafo respondem perguntas sobre documentos. Eles não guardam o trabalho de síntese. Quando um leitor faz uma pergunta que cruza vários livros, o sistema refaz a leitura dos trechos a cada vez.

O padrão LLM-Wiki propõe outro caminho. O modelo mantém uma wiki persistente de arquivos Markdown. Cada fonte nova é integrada às páginas existentes. As referências cruzadas ficam prontas. As contradições ficam registradas.

O Open Knowledge Format (OKF) v0.2 dá o formato desses arquivos. A especificação está em `https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`. Um bundle OKF é um diretório de arquivos Markdown com frontmatter YAML. O campo `type` é o único obrigatório. A versão 0.2 acrescenta `sources`, `generated`, `verified`, `status` e `stale_after`. Os nomes `index.md` e `log.md` são reservados.

## Decisão

1. O módulo `vlade_rag.okf` lê e escreve conceitos OKF v0.2. Ele usa PyYAML pelo extra `okf`, com licença MIT. Sem o extra, o módulo importa, mas as chamadas de leitura e escrita avisam que falta o extra.
2. O parser de Markdown aproveita o frontmatter OKF. Os campos entram nos metadados do documento com o prefixo `okf_`. O texto indexado fica sem o frontmatter.
3. O port `WikiStore` guarda páginas por tenant e por base. O adapter padrão usa o sistema de arquivos em `VLADE_WIKI__ROOT`. O adapter em memória serve para testes. O grafo e a wiki ficam desligados por padrão.
4. Os casos de uso de `core/application/wiki.py` cobrem leitura, escrita, exclusão, geração e lint. A geração recupera trechos da base, chama o LLM com o prompt `wiki_synthesis` e grava uma página com citações ligadas aos documentos de origem.
5. O lint confere links quebrados, páginas órfãs, `stale_after` vencido e a presença de `index.md` e `log.md`. Ele não usa LLM. A detecção de contradições entre páginas fica para uma versão futura.
6. A API acrescenta rotas de wiki. O MCP acrescenta as ferramentas `vlade_wiki_read`, `vlade_wiki_lint`, `vlade_wiki_write` e `vlade_wiki_synthesize`. Elas aparecem só quando o servidor tem um `WikiStore`.
7. A geração de páginas usa o modelo de geração da base. O modelo de extração do grafo continua separado. Um provedor remoto responde pelas duas chamadas.

## Alternativas avaliadas

- **Guardar a wiki dentro da base de documentos:** mistura fontes imutáveis e conteúdo gerado. A origem de uma afirmação ficaria menos clara.
- **Usar um banco de grafos para a wiki:** o OKF pede arquivos Markdown portáteis. Um banco próprio quebraria a troca de bundles entre sistemas.
- **Gerar a resposta final a cada pergunta:** é o comportamento atual da busca híbrida. Não acumula conhecimento entre perguntas.

## Consequências

- O conteúdo gerado fica em arquivos legíveis e versionáveis. Um bundle OKF pode sair do projeto sem conversão.
- A wiki consome chamadas de LLM na geração de cada página. O custo cresce com o número de páginas e de fontes.
- O isolamento das páginas vem do diretório por tenant e pela base. Ele não tem RLS. O teste de unidade cobre o isolamento.
- A v1 do projeto não tem human-in-the-loop (ADR-0014). O campo `verified` do OKF permite marcar revisão humana, mas o servidor não exige essa revisão antes de publicar.
- O campo `verified` é um sinal de confiança, não uma permissão. Uma página sem `verified` continua legível, conforme a conformance do OKF v0.2.
