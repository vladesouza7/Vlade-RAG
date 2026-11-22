# Consumo de memória do perfil `dev` (RNF-11)

> Medido em 2026-11-21. Dados brutos em [`memory.json`](memory.json).

## Critério

O consumo de memória do perfil `dev` fica em até 3 GB, sem Ollama (ROADMAP, fase 0).

## Método

1. Subir os serviços do perfil `dev`: `docker compose --profile dev up -d api`. Os serviços são `api`, `postgres` e `valkey`. O serviço `migrate` termina antes do início da medição.
2. Criar uma base com embeddings `hashing` e ingerir quatro documentos de 40 blocos de texto. A API roda o worker de ingestão embutido no perfil `dev`.
3. Fazer 25 segundos de buscas com oito requisições concorrentes. As 550 buscas receberam HTTP 200, sem falha.
4. Amostrar `docker stats --no-stream` a cada volta do laço. O comando leva cerca de 3 segundos nesta máquina, de modo que a janela tem oito amostras.
5. Somar o uso de memória dos três serviços do perfil `dev`. O Phoenix, de outro perfil, é medido à parte.

## Resultado

| Serviço | Limite | Pico observado |
|---|---:|---:|
| `api` | 768 MiB | 73,96 MiB |
| `postgres` | 1 GiB | 84,38 MiB |
| `valkey` | 320 MiB | 8,11 MiB |
| **Total do perfil `dev`** | **2112 MiB** | **165,86 MiB** |

O pico fica muito abaixo de 3072 MiB. O critério passa com folga. O maior consumo individual é o do PostgreSQL, que sobe quando o cache de páginas cresce durante as buscas.

O Phoenix, ligado com `--profile phoenix`, usou 469,5 MiB. Somado ao perfil `dev`, o total foi 635,69 MiB. O perfil `ollama` não entrou na medição, conforme o critério.

## Limitações

- A imagem `vlade-rag:dev` já estava construída nesta máquina. A medição usa essa imagem, e não um build novo do código local.
- O conjunto de dados é pequeno: quatro documentos e uma base. A medida mostra o consumo do perfil em repouso e sob busca leve, não o pico de uma ingestão longa.
- `docker stats` informa o uso de memória de cada container. A soma não inclui o overhead do daemon do Docker nem a memória do host usada pelo WSL.
- A janela de amostragem tem oito pontos por causa do custo do comando. Um pico mais curto pode não aparecer.

## Uso

Esta medida não destrava a tarefa 4.1 nem a 4.5 por si só. Ela só fecha o critério RNF-11 que estava pendente desde a fase 0. Antes das tarefas seguintes, vale repetir a medição com a imagem reconstruída e com um conjunto de dados maior.
