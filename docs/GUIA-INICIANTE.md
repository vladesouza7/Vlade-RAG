# Guia do iniciante

Este manual ajuda você a entender o Vlade-RAG e a fazer um primeiro teste. O texto usa linguagem simples e parte do zero.

> Situação do projeto em 24/11/2026: fase 5 (Extensões) em andamento. O projeto concluiu as fases 0 e 4. A equipe integrou as fases 1, 2 e 3 na branch `homolog`. Veja o [roadmap](ROADMAP.md).

## 1. O que é o Vlade-RAG

O Vlade-RAG é um framework open source de Retrieval-Augmented Generation (RAG). Ele oferece um núcleo reutilizável para ingestão, indexação, recuperação, geração e avaliação de respostas.

O projeto não é um chatbot pronto. Ele é a base para criar uma aplicação com base de conhecimento. A aplicação troca provedores por configuração: LLM, embeddings, reranker, banco vetorial, estratégia de chunking e fontes de documentos.

O núcleo funciona de quatro formas:

- Biblioteca Python, sem servidor.
- API REST, com documentação interativa.
- CLI, pelo comando `vlade-rag`.
- Servidor MCP, para agentes e clientes que usam o protocolo MCP.

Cada tenant tem uma base isolada. A chave de API define o tenant e os papéis do usuário.

## 2. Para que serve

O Vlade-RAG serve para aplicações que respondem perguntas usando documentos próprios. Exemplos:

- Assistentes de atendimento e de vendas.
- Consulta a documentos de empresas.
- Assistentes jurídicos e administrativos.
- Bases de conhecimento corporativas.
- Agentes de IA que precisam de documentos internos, por MCP.
- Sistemas multi-tenant, com uma base isolada por empresa.

## 3. Qual problema o projeto resolve

Um modelo de linguagem não conhece os documentos privados de uma empresa. Quando não sabe a resposta, ele pode inventar uma informação.

Montar um sistema RAG do zero exige trabalho repetido. É preciso ler PDFs e HTML. Também é preciso dividir o texto, gerar vetores e escolher um banco vetorial. É preciso buscar por palavra e por vetor, montar o contexto e citar as fontes. Ainda é preciso medir a qualidade, isolar clientes, controlar cotas e auditar ações.

O Vlade-RAG entrega esse trabalho pronto e modular. Os componentes seguem o padrão ports and adapters. Para trocar de provedor, você muda a configuração. Você não precisa mudar a lógica da aplicação.

A resposta vem com citação. Cada citação aponta para o trecho que contém a informação. Se o trecho não aparece nas fontes, o sistema informa que não encontrou a informação. Ele não inventa uma resposta.

O projeto também mede a qualidade. As métricas incluem Recall@10, MRR, NDCG e faithfulness. O gate de qualidade na CI detecta regressões antes de uma mudança entrar.

## 4. O que é preciso para testar

- Docker com Compose 2.20 ou mais recente.
- Docker em execução.
- Uma chave de provedor remoto de modelos, por exemplo OpenRouter ou OpenAI, com saldo disponível.
- Memória RAM: 8 GB são suficientes quando os modelos ficam no provedor remoto. O consumo medido do perfil `dev` fica abaixo de 3 GB.
- Opcional: `uv` e Rust, só para desenvolvimento ou para compilar o motor nativo fora do Docker.

Evite modelos locais no primeiro teste. O perfil `ollama` baixa modelos grandes e exige mais memória e CPU.

## 5. Exemplo simples: da pilha até a primeira resposta

Os comandos abaixo usam o Linux. No Windows, rode-os dentro do WSL.

### Passo 1 — Configure o arquivo `.env`

```bash
cp .env.example .env
```

Preencha no arquivo `.env`:

- `POSTGRES_PASSWORD`, `VLADE_APP_DB_PASSWORD` e `VLADE_API_KEY_PEPPER`: segredos do serviço.
- `OPENROUTER_API_KEY` ou a chave do provedor que você escolheu.
- `VLADE_DEFAULT_KB_CONFIG`: configuração das bases novas. Use uma linha JSON:

```json
{"embeddings": {"provider": "openrouter", "model": "openai/text-embedding-3-small", "dimension": 1536}, "generation": {"provider": "openrouter", "model": "tencent/hy4-flash"}}
```

Atenção: se você deixar `VLADE_DEFAULT_KB_CONFIG={}`, o sistema usa os valores padrão de Ollama. Se você fizer isso, o Ollama precisa rodar na máquina.

### Passo 2 — Suba a API

```bash
docker compose --profile dev up -d --build api
```

O comando cria o banco, aplica as migrações e inicia a API. No perfil `dev`, a API também executa o worker de ingestão.

### Passo 3 — Crie um tenant e uma chave de API

```bash
docker compose exec api vlade-rag tenant create minha-empresa
docker compose exec api vlade-rag key create --tenant minha-empresa --roles admin
```

Guarde a chave exibida. O sistema mostra o segredo uma única vez.

### Passo 4 — Crie uma base de conhecimento

```bash
export KEY=vrag_...
curl -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"slug": "docs", "name": "Documentos"}' \
  http://localhost:8000/v1/knowledge-bases
```

### Passo 5 — Envie um documento pequeno

Crie um arquivo chamado `manual.md` com este conteúdo:

```markdown
# Entrega

O prazo de entrega é de 5 dias úteis após a confirmação do pedido.
```

Envie o arquivo:

```bash
curl -H "Authorization: Bearer $KEY" -F "file=@manual.md" \
  http://localhost:8000/v1/knowledge-bases/docs/documents
```

Aguarde alguns segundos. A ingestão divide o arquivo em trechos e gera os vetores.

### Passo 6 — Faça a pergunta

```bash
curl -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"question": "Qual é o prazo de entrega?"}' \
  http://localhost:8000/v1/knowledge-bases/docs/query
```

A resposta traz o texto gerado e as citações. A citação aponta para o trecho do `manual.md` que contém o prazo de entrega.

Você também pode fazer os passos 4, 5 e 6 no navegador. Abra `http://localhost:8000/docs`, clique em **Authorize**, informe a chave e use o botão **Try it out** de cada endpoint.

## 6. Como verificar o resultado

| Verificação | Como fazer | Resultado esperado |
|---|---|---|
| API no ar | Abra `http://localhost:8000/health/live` | `{"status":"ok","version":"0.0.1","native_backend":"rust"}` |
| Documentação da API | Abra `http://localhost:8000/docs` | Lista de endpoints do Vlade-RAG |
| Logs da API | `docker compose logs -f api` | Eventos de inicialização e de requisições |
| Estado dos serviços | `docker compose --profile dev ps` | Container `api` com status `healthy` |
| Versão e motor nativo | `docker compose exec api vlade-rag version` | Versão do pacote e backend ativo |

Quando os perfis `prod` e `phoenix` estão ativos, o Grafana responde em `http://localhost:3000` e o Phoenix em `http://localhost:6006`.

## 7. Problemas comuns

| Sintoma | Causa provável | Ação |
|---|---|---|
| `Failed to fetch` no Swagger, no Windows com WSL2 | O Compose publica a porta da API só no loopback interno do WSL | Crie um arquivo local `docker-compose.override.yaml` com o conteúdo abaixo. Depois rode `docker compose --profile dev up -d api` |
| Resposta diz que não encontrou a informação | O documento ainda está em processamento, a chave do provedor está sem saldo, ou a configuração das bases ficou com o padrão de Ollama | Aguarde o job, confira o saldo da chave e preencha `VLADE_DEFAULT_KB_CONFIG` |
| Porta 8000 ocupada | Outro serviço usa a porta | Mude `VLADE_API_HOST_PORT` no `.env` |
| Falta de memória | Perfis com modelos locais ou com observabilidade ativos | Use somente o perfil `dev` no primeiro teste |

Conteúdo do `docker-compose.override.yaml` para WSL2:

```yaml
services:
  api:
    ports: !override
      - "0.0.0.0:8000:8000"
```

Esse arquivo é um ajuste local. Ele não precisa entrar no repositório.

## 8. Continue por aqui

| Documento | O que você encontra |
|---|---|
| [README](../README.md) | Visão geral, instalação e exemplos de API |
| [Roadmap](ROADMAP.md) | Fases, tarefas e situação atual |
| [Requisitos](PROJECT_SPEC.md) | Casos de uso e requisitos funcionais e não funcionais |
| [Arquitetura](ARCHITECTURE.md) | Ports, adapters, pipeline e persistência |
| [Guia de implantação](operacao/implantacao.md) | Perfis do Compose, variáveis e operação |
| [Contrato do MCP](MCP_SPEC.md) | Ferramentas, papéis e transportes do servidor MCP |
| [Decisões de arquitetura](adr/README.md) | Motivo de cada decisão técnica |
| [Especificação mestre](../VLADE-RAG.md) | Descrição completa do projeto |

O código usa a licença MIT.
