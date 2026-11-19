# ADR-0011: Kestra para operação, LangGraph para consulta, fila no PostgreSQL

- Status: Aceito
- Data: 2026-11-19

## Contexto

O Vlade-RAG tem dois tipos de fluxo. Fluxos operacionais duram minutos ou horas e rodam por agenda ou evento: ingestão em lote, reindexação, avaliação, backup. Fluxos de consulta duram segundos e rodam a cada pergunta. O rascunho original previa Celery e Redis e depois trocou por Kestra.

## Decisão

1. O Kestra orquestra os fluxos operacionais. Os flows chamam a API REST do Vlade-RAG. Os flows não acessam o banco diretamente.
2. O fluxo de consulta tem duas implementações: um pipeline linear em Python puro (padrão) e um grafo LangGraph (opcional).
3. O Kestra não fica no caminho de uma consulta síncrona.
4. A fila de jobs de ingestão é a tabela `ingestion_jobs`, com `FOR UPDATE SKIP LOCKED`. O processo `vlade-rag worker` consome a fila.
5. A versão 1 não usa Celery.

## Alternativas avaliadas

- **Celery com Redis:** maduro, mas duplica o papel do Kestra e acrescenta um serviço.
- **Fila no Valkey:** rápida, mas o estado do job ficaria em dois lugares.
- **LangGraph obrigatório:** fluxos condicionais nativos, mas acopla o núcleo a uma biblioteca externa.

## Consequências

- O perfil `dev` funciona sem Kestra, com o worker dentro do processo da API.
- O estado de cada job fica em uma transação com os dados do job.
- Se a vazão da fila no PostgreSQL não bastar, um ADR novo avalia outra fila.
