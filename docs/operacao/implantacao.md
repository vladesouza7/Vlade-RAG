# Guia de implantação

Este guia descreve como implantar o Vlade-RAG com Docker Compose. Ele cobre a instalação inicial, a verificação, a operação diária e a atualização.

## Pré-requisitos

- Docker Engine 24 ou mais recente, com o plugin Compose.
- Docker com 8 GB de memória livre para o perfil `prod`. O perfil `dev` precisa de 3 GB.
- Acesso ao repositório e um arquivo `.env` na raiz.
- Uma chave de cada provedor de LLM e embeddings que a instalação usa. O modo local com Ollama não precisa de chave.
- Portas livres no host. O Compose publica as portas em `127.0.0.1`.

O arquivo do Compose fica em `deploy/compose/docker-compose.yml`. Execute os comandos abaixo na raiz do repositório.

## Variáveis de ambiente

Copie o modelo e preencha os valores:

```bash
cp .env.example .env
```

| Variável | Uso |
|---|---|
| `POSTGRES_PASSWORD` | Senha do dono do PostgreSQL |
| `VLADE_APP_DB_PASSWORD` | Senha do papel da aplicação |
| `VLADE_API_KEY_PEPPER` | Segredo usado no hash das chaves de API |
| `S3_ACCESS_KEY_ID` e `S3_SECRET_ACCESS_KEY` | Credenciais do RustFS ou do S3 |
| `VLADE_OTEL__ENABLED` | Liga traces e métricas. Use `true` em `prod` |
| `VLADE_OTEL__ENDPOINT` | Use `http://alloy:4318` no Compose |
| `GRAFANA_ADMIN_PASSWORD` | Senha do administrador do Grafana |
| `VLADE_PROVIDERS__*` | Chaves e URLs dos provedores |
| `VLADE_SOURCES__ALLOWED_DOMAINS` | Domínios permitidos para `https://` e para o conector de sites (ADR-0028) |
| `VLADE_SOURCES__WEB__SEEDS`, `VLADE_SOURCES__GOOGLE_DRIVE__ACCESS_TOKEN`, `VLADE_SOURCES__SQL__URL` | Ligam os conectores de origem (ADR-0029) |
| `VLADE_CACHE__SEMANTIC__*` | Ligam e ajustam o cache semântico de consultas (ADR-0030) |

Gere senhas e pepper com um gerador aleatório. Nunca use os valores do `.env.example` em `prod`. O Compose usa `admin` como senha do Grafana quando `GRAFANA_ADMIN_PASSWORD` está vazia. Troque essa senha antes de subir o perfil `prod`.

## Perfis

| Perfil | Serviços | Uso |
|---|---|---|
| `dev` | API com worker, PostgreSQL, Valkey e RustFS opcional | Desenvolvimento |
| `staging` | API, worker, MCP e o Alloy para backends externos | Homologação |
| `prod` | API, worker, MCP, pilha LGTM e exporters | Produção |

O perfil `prod` sobe o Alloy, o Prometheus, o Loki, o Tempo, o Grafana e os exporters de infraestrutura. O perfil `staging` sobe só o Alloy entre os serviços de observabilidade.

## Instalação inicial

1. Confira a sintaxe do Compose:

   ```bash
   docker compose -f deploy/compose/docker-compose.yml --profile prod config --quiet
   ```

2. Suba os serviços:

   ```bash
   docker compose -f deploy/compose/docker-compose.yml --profile prod up -d
   ```

   O serviço `migrate` aplica as migrações antes da API. O worker e o MCP esperam a migração terminar.

3. Acompanhe o início:

   ```bash
   docker compose -f deploy/compose/docker-compose.yml --profile prod ps
   docker compose -f deploy/compose/docker-compose.yml logs -f api worker
   ```

4. Confira a saúde dos serviços:

   ```bash
   curl -fsS http://127.0.0.1:8000/health/live
   curl -fsS http://127.0.0.1:8000/health/ready
   curl -fsS http://127.0.0.1:9090/-/ready
   curl -fsS http://127.0.0.1:3100/ready
   curl -fsS http://127.0.0.1:3200/ready
   curl -fsS http://127.0.0.1:3000/api/health
   ```

   O endpoint `/health/ready` confere PostgreSQL, armazenamento de objetos e cache. Ele falha se um desses serviços estiver indisponível.

## Configuração inicial

Crie um tenant, uma chave de API e uma base de conhecimento. Use a CLI dentro de um container da aplicação:

```bash
docker compose -f deploy/compose/docker-compose.yml exec api \
  vlade-rag tenant create acme --name "ACME"

docker compose -f deploy/compose/docker-compose.yml exec api \
  vlade-rag key create --tenant acme --roles admin --name bootstrap

docker compose -f deploy/compose/docker-compose.yml exec api \
  vlade-rag kb create juridic --config /data/objects/kb.json
```

A CLI mostra a chave uma vez. Guarde-a em um cofre de segredos. O token pertence ao tenant que a chave identifica.

Para configurar uma base, use um arquivo JSON com embeddings, recuperação e geração. Os exemplos estão em `deploy/examples/`. A arquitetura descreve cada campo na seção 9.2.

## Observabilidade

O Grafana fica em `http://127.0.0.1:3000`. Use o usuário `admin` e a senha do `.env`. A pasta `Vlade-RAG` contém cinco dashboards:

| Dashboard | Conteúdo |
|---|---|
| RAG Performance | Latência, vazão e qualidade das respostas |
| LLM Observability | Tokens, custo estimado e erros |
| Retrieval Analytics | Resultados por retriever e latência das etapas |
| Infrastructure | CPU, memória, disco e bancos |
| Workflow Monitoring | Fila, jobs, etapas e alertas |

O Prometheus carrega oito alertas. Cada alerta tem um teste de falha provocada em `tests/promtool/alerts.test.yml`. A documentação da pilha está em `deploy/observability/README.md`.

As portas escutam em `127.0.0.1`. Para acessar o Grafana de outra máquina, use um proxy reverso com TLS e autenticação. Não publique as portas do Prometheus, do Loki e do Tempo.

## Operação diária

Os comandos de manutenção ficam no módulo `ops`:

```bash
docker compose -f deploy/compose/docker-compose.yml exec api vlade-rag ops health
docker compose -f deploy/compose/docker-compose.yml exec api vlade-rag ops recover-jobs
docker compose -f deploy/compose/docker-compose.yml exec api vlade-rag ops cleanup
```

O comando `health` mostra as verificações de prontidão. O comando `recover-jobs` devolve para o worker os jobs com lease vencido. O comando `cleanup` apaga espaços órfãos e versões antigas. Execute os dois últimos em um job agendado.

O Kestra roda os flows de ingestão, reindexação, avaliação e backup. Os arquivos estão em `deploy/kestra/flows/`. Os gatilhos diários começam desligados. Ligues-os depois de conferir as credenciais do Kestra.

## Atualização

1. Leia o `CHANGELOG.md` e as migrações do release.
2. Faça backup do PostgreSQL e do armazenamento de objetos.
3. Baixe a versão nova e pare a aplicação:

   ```bash
   git pull origin homolog
   docker compose -f deploy/compose/docker-compose.yml --profile prod build api worker mcp migrate
   docker compose -f deploy/compose/docker-compose.yml --profile prod up -d
   ```

4. Confira `/health/ready` e os dashboards.
5. Se o release mudou embeddings ou chunking, faça uma reindexação. Use `POST /v1/knowledge-bases/{kb}/reindex` com `confirm`. A busca continua durante a reindexação.

O Compose mantém os volumes `pgdata`, `objects`, `prometheusdata`, `lokidata`, `tempodata` e `grafanadata`. Não use `down --volumes` em produção.

## Backup e restauração

O flow `backup` do Kestra copia o banco e os objetos. Guarde as cópias fora do host. O `.env` contém senhas, mas não faz parte do backup do banco. Guarde-o em um cofre separado.

Para restaurar, pare a API e o worker. Restaure o PostgreSQL e o bucket de objetos. Depois suba os serviços e rode `vlade-rag db upgrade`. Confira a saúde e uma busca em cada base.

## Segurança

- Use TLS no proxy reverso e nas conexões com provedores.
- Troque as senhas padrão e revogue chaves antigas.
- O Alloy lê o socket do Docker em modo somente leitura. Restrinja o acesso ao arquivo do Compose.
- O `cadvisor` roda como privilegiado. Remova-o se a política da máquina não permitir.
- O `tenant_id` fica nos traces e nos logs. Ele não entra em rótulos de métrica.
- O texto de perguntas e respostas entra nos spans só com `VLADE_LIMITS__STORE_QUERY_TEXT=true`. Desligue esse recurso em dados sensíveis.

## Solução de problemas

| Sintoma | Ação |
|---|---|
| `/health/ready` falha | Veja os logs da API. Confira as credenciais do banco, do bucket e do cache |
| API sem traces | Confira `VLADE_OTEL__ENABLED`, o endpoint do Alloy e os logs do coletor |
| Prometheus sem métricas da aplicação | Veja se o endpoint de escrita remota do Alloy responde |
| Dashboard sem dados | Confira o seletor de tempo e se o painel depende de uma falha |
| Fila crescendo | Veja os logs do worker e rode `vlade-rag ops recover-jobs` |
| Loki sem logs | Confira se o Alloy lê o socket do Docker e se os containers têm o rótulo do projeto |
| Grafana sem dashboards | Confira os logs do provisionador e se a pasta `grafana/dashboards/` existe |
