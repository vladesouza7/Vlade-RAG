# ADR-0027: Reindexação sem parada

- Status: Aceito
- Data: 2026-11-21

## Contexto

A seção 13 do `ARCHITECTURE.md` define dois modos de reindexação. O modo `embeddings` troca o modelo de embeddings e mantém os chunks. O modo `full` processa de novo os arquivos originais, por exemplo para um chunking novo. O critério de aceite da fase 4 diz: uma reindexação completa roda enquanto um teste de carga faz consultas, nenhuma consulta falha e nenhuma consulta mistura espaços de embeddings.

A seção 13 não diz o que acontece com uma ingestão que corre ao mesmo tempo que a reindexação. Dois casos quebram o critério:

1. Um documento publicado durante a construção do espaço novo não tem vetor no espaço novo. Depois da troca, a busca vetorial não encontra esse documento.
2. Uma ingestão grava os vetores no espaço ativo e publica a versão. Se a troca acontece entre as duas etapas, a versão fica publicada com vetores só no espaço antigo.

## Decisão

1. **Caso de uso.** `ReindexKnowledgeBase` recebe a base, o modo e uma configuração parcial, mesclada sobre a atual: `embeddings` no modo `embeddings` e `chunking` no modo `full`. Sem `confirm`, ele devolve uma prévia com documentos, chunks publicados e chamadas de embeddings estimadas. Com `confirm`, ele cria um job `reindex`. Se já existe um job `reindex` pendente ou em execução para a base, ele devolve `conflict`. Um índice único no banco impede que duas requisições concorrentes criem dois jobs. Ele exige o papel `admin` e grava um evento de auditoria.
2. **Modo `embeddings`.** O worker cria um espaço com status `building` e gera os vetores de todos os chunks publicados, em lotes de 512 chunks. As buscas continuam no espaço ativo. Depois, o worker faz uma passada pelos chunks publicados sem vetor no espaço novo. Em seguida, ele troca o espaço numa transação. A transação trava a linha da base e confere que nenhum chunk publicado está sem vetor. Depois, ela troca `active_embedding_space_id` e `config.embeddings`, marca o espaço novo como `active` e o antigo como `retired`, e aumenta `kb_epoch`.
3. **Corrida 1 (documento publicado durante a construção).** Se a conferência da troca acha chunks sem vetor, a troca devolve `MissingVectors`. O worker gera os vetores que faltam e tenta de novo, até 5 vezes.
4. **Corrida 2 (publicação depois da troca).** A publicação de uma versão recebe o espaço em que a ingestão gravou os vetores. Ela trava a mesma linha da base e compara esse espaço com o espaço ativo. Se ele mudou, a publicação devolve `EmbeddingSpaceChanged`. A ingestão lê a base de novo, gera os vetores com o modelo novo no espaço novo e publica, até 3 vezes. A troca e a publicação usam a mesma trava, então uma sempre vê o resultado da outra.
5. **Modo `full`.** O worker cria para cada documento publicado uma versão nova, com o mesmo arquivo original, e um job de ingestão. O job leva o chunking novo e a versão que ele pode substituir. Se outra versão já substituiu a original, o job não publica. O job registra um passo por documento. Se o worker cai e a fila devolve o job, ele não cria uma versão nova para um documento já enfileirado. O worker grava o chunking novo na configuração da base depois de criar todos os jobs. Assim, uma falha no meio do caminho não deixa a base reprocessada só em parte. O modo `full` não muda o modelo de embeddings: para isso, rode antes o modo `embeddings`.
6. **Espaço antigo.** O espaço antigo fica com status `retired`, com os vetores e o índice. Se o worker cai durante a construção, o espaço `building` fica órfão. O módulo `ops` (tarefa 4.4) apaga os espaços `retired` e os espaços `building` órfãos depois de um período de espera.
7. **Interfaces.** `POST /v1/knowledge-bases/{kb}/reindex` e `vlade-rag reindex <base> --mode embeddings|full [--confirm] [--wait]`. A ferramenta MCP `vlade_reindex_knowledge_base` entra com as ferramentas de escrita (tarefa 4.3).

## Alternativas avaliadas

- **Escrita dupla durante a construção:** cada ingestão gravaria vetores nos dois espaços. Isso resolve a corrida 1, mas não a corrida 2, e dobra o custo das ingestões durante a reindexação. Recusado.
- **Bloquear as ingestões durante a reindexação:** simples, mas a base fica sem ingestão por todo o tempo da reindexação, que pode levar horas. Recusado.
- **Trocar o espaço sem conferência:** os chunks publicados durante a construção ficariam sem vetor no espaço novo. Recusado.
- **Modo `full` com troca atômica da base inteira:** exige duas cópias completas dos chunks e uma troca de todas as versões numa transação. A seção 13 aceita a troca por documento. Recusado.

## Consequências

- Durante o modo `full`, a base tem documentos com o chunking antigo e documentos com o chunking novo, como a seção 13 diz.
- A publicação de uma versão trava a linha da base por um momento. Ingestões em paralelo na mesma base publicam uma de cada vez.
- O espaço `retired` ocupa memória e disco até a limpeza da tarefa 4.4. O mesmo vale para um espaço `building` de um job interrompido.
- O caso de uso de atualização da configuração (seção 9.2) ainda não existe. Por enquanto, a reindexação é o único caminho para mudar o modelo de embeddings ou o chunking de uma base.
