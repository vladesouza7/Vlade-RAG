# ADR-0029: Conectores de origem

- Status: Aceito
- Data: 2026-11-23

## Contexto

O port `DocumentSource` existe desde a fase 0, mas não tinha adapter nem consumidor. A ferramenta MCP `vlade_ingest_document` lê só `s3://` e `https://` (ADR-0028). A tarefa 5.2 pede conectores para Google Drive, sites e bancos SQL, e a tarefa 5.3 pede um flow `sync_source`.

Uma ingestão repetida não pode criar documentos duplicados. Um conector também não pode ler uma rede interna nem escrever em um banco externo.

## Decisão

1. **Porta.** Os três conectores implementam `DocumentSource`: `WebSource`, `GoogleDriveSource` e `SqlSource`. Cada um expõe `list_items` e `fetch`. O `Runtime` guarda os conectores em `deps.document_sources`, ligados por nome.
2. **Sites.** `WebSource` começa de sementes HTTPS, segue links do mesmo host até uma profundidade e um número máximo de páginas. Ele reusa o download seguro da ADR-0028: lista de domínios, porta 443, sem redirecionamento, sem endereço privado e limite de tamanho. O HTML é convertido em documento por um analisador da biblioteca padrão.
3. **Google Drive.** `GoogleDriveSource` usa a API Drive v3 com um token OAuth de acesso fornecido pelo operador. Ele lista arquivos de uma pasta e baixa cada arquivo por id. O token fica em `SecretStr` e não entra em log nem em auditoria.
4. **Banco SQL.** `SqlSource` executa uma única consulta `SELECT`, `WITH` ou `VALUES`, sem ponto e vírgula no meio. Ele usa SQLAlchemy no extra `sql` e converte cada linha em um documento JSON. A consulta deve usar um papel de banco somente leitura. O extra inclui `aiosqlite` para testes e desenvolvimento local. Outros drivers ficam a cargo do operador.
5. **Sincronização.** O caso de uso `SyncSource` lista os itens e chama `SubmitIngestion` para cada um. Ele conta só os documentos novos. O `external_id` de cada item permite que uma segunda execução pule os documentos inalterados.
6. **Configuração.** Os conectores ficam desligados por padrão. `VLADE_SOURCES__WEB__SEEDS`, `VLADE_SOURCES__GOOGLE_DRIVE__ACCESS_TOKEN` e `VLADE_SOURCES__SQL__URL` com `VLADE_SOURCES__SQL__QUERY` ligam cada um.
7. **Contrato.** `tests/contract/test_document_source.py` executa os mesmos testes nos três adapters com clientes falsos. `tests/unit/test_sync_source.py` cobre o caso de uso e a deduplicação.

## Alternativas avaliadas

- **Estender só `read_source` com novos esquemas de URI:** cobriria o MCP, mas não permitiria listar o conteúdo de uma pasta, de um site ou de uma consulta. Recusado.
- **Usar a biblioteca cliente do Google Drive:** traria dependências pesadas. A API REST com `httpx2` atende a listagem e o download com o token do operador.
- **Usar SQLAlchemy no adapter interno do PostgreSQL:** o ADR-0016 escolhe SQL direto por causa de RLS e funções `SECURITY DEFINER`. O conector SQL lê um banco externo e usa SQLAlchemy só nesse extra.
- **Buscar o token do Drive em uma conta de serviço:** exigiria credenciais de longa duração e mais dependências. O token de acesso pode ser renovado por um cofre externo.

## Consequências

- O conector de sites depende da lista de domínios da ADR-0028. Sem ela, nenhuma semente é lida.
- O token do Drive expira. O operador precisa renová-lo no cofre de segredos.
- O conector SQL não garante que a consulta é segura no banco. Ele valida a forma da instrução. A permissão de leitura no banco é a barreira real.
- O endpoint `POST /v1/knowledge-bases/{kb}/sources/{source}/sync` expõe a sincronização. O flow `sync_source` chama esse endpoint e começa com o gatilho desligado.
- A suíte de contrato roda sem rede e sem serviços externos.
- A limitação L23 da ADR-0028 continua válida para o conector de sites.
