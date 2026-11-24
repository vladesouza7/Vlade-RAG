# Flows Kestra

Os cinco flows executam as tarefas operacionais das tarefas 4.1 e 5.3 (ADR-0011 e ADR-0029). Eles ficam em `deploy/kestra/flows/` e chamam a API REST do Vlade-RAG com uma chave de serviço do tenant. O único fluxo que não chama a API é `backup`, que usa credenciais de operação diretas.

| Flow | Gatilho | Ação |
|---|---|---|
| `ingest_batch` | Manual ou evento de objeto | Envia um lote de documentos com `POST /v1/knowledge-bases/{kb}/documents` |
| `sync_source` | Agenda diária (desligada por padrão) | Chama `POST /v1/knowledge-bases/{kb}/sources/{source}/sync` |
| `reindex_knowledge_base` | Manual | Faz a prévia, confirma com `POST /v1/knowledge-bases/{kb}/reindex` e espera o job |
| `evaluate_nightly` | Agenda diária (desligada por padrão) | Chama `POST /v1/evaluations` e espera o job |
| `backup` | Agenda diária (desligada por padrão) | Faz `pg_dump` e copia o bucket de objetos |

## Variáveis e segredos

Os flows leem estes valores do namespace Kestra `vlade`:

| Nome | Tipo | Uso |
|---|---|---|
| `vars.vlade_api_url` | variável | URL base da API, por exemplo `http://api:8000` |
| `vars.vlade_backup_db_host`, `vars.vlade_backup_bucket`, `vars.vlade_backup_s3_region`, `vars.vlade_backup_source_alias`, `vars.vlade_backup_target_alias`, `vars.vlade_object_bucket` | variáveis | Destino do backup |
| `secrets.VLADE_API_KEY` | segredo | Chave de serviço com papel `admin` no tenant |
| `secrets.VLADE_BACKUP_DB_PASSWORD`, `secrets.VLADE_BACKUP_S3_ACCESS_KEY`, `secrets.VLADE_BACKUP_S3_SECRET_KEY` | segredos | Credenciais do backup |

As chaves de serviço são criadas com `vlade-rag key create --tenant <slug> --roles admin --name kestra`. O valor vai para o cofre do Kestra, nunca para o arquivo do flow.

O registro de datasets fica no servidor da API, em `VLADE_EVALUATION__DATASETS_PATH`. Em `staging` e `prod`, esse diretório precisa ser montado no container da API: a imagem não inclui os datasets do repositório.

## Carga e agendamento

`ingest_batch` recebe `documents` como uma string JSON:

```json
[{"filename": "manual.md", "content_text": "# Manual\n\nTexto do manual."}]
```

`sync_source` recebe `source` e `knowledge_base`. Os parâmetros `cursor` e `limit` são opcionais. O conector precisa estar configurado no servidor da API antes de ligar o gatilho.

Os gatilhos de `sync_source`, `evaluate_nightly` e `backup` vêm com `disabled: true`. O operador liga cada um depois de definir os segredos e as variáveis, e de conferir a janela de execução.

## Verificação

Não há servidor Kestra no perfil `dev`. A suíte `tests/unit/test_kestra_flows.py` confere a estrutura dos cinco arquivos, os gatilhos, os inputs e as chamadas à API. A aceitação de reindexação sob carga roda no teste `tests/integration/test_reindex_load.py`, que faz buscas e reindexação em paralelo.
