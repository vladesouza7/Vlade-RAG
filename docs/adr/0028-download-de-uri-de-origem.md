# ADR-0028: Download de URI de origem

- Status: Aceito
- Data: 2026-11-21

## Contexto

A seção 5.7 do `MCP_SPEC.md` define a ferramenta `vlade_ingest_document`. O agente envia o texto em `content_text` ou um endereço em `source_uri`. O endereço aceita `s3://` no bucket do tenant e `https://`. A seção 15 do `ARCHITECTURE.md` exige: download por URL desativado por padrão, lista de domínios permitidos quando ativo e bloqueio de endereços privados e de link-local.

O servidor não tem ainda política para esse download. Aceitar qualquer URL deixaria um cliente MCP pedir ao servidor que lesse a rede interna (SSRF). Aceitar qualquer bucket deixaria um tenant ler objetos de outro tenant.

## Decisão

1. **Configuração.** `VLADE_SOURCES__ALLOWED_DOMAINS` é uma lista de nomes de domínio. A lista vazia é o padrão e recusa todo `https://`. Um nome permite o domínio exato e os subdomínios. `VLADE_SOURCES__MAX_BYTES` e `VLADE_SOURCES__TIMEOUT` limitam o download.
2. **`https://`.** A ferramenta exige a porta 443, sem usuário e sem senha. Ela recusa redirecionamentos. Antes da requisição, ela resolve o nome e recusa o endereço quando ele não é global ou quando é multicast. Ela lê o corpo em blocos e para quando passa do limite de tamanho. O tipo MIME declarado pelo servidor é repassado ao caso de uso `SubmitIngestion`, que confere o conteúdo.
3. **`s3://`.** A ferramenta exige o bucket configurado no servidor e uma chave começando pelo id do tenant. O adapter de armazenamento de objetos lê a chave restante. Com outro backend que não seja S3, a ferramenta recusa a URI. Não existe caminho para ler o bucket de outro tenant.
4. **Erros.** Domínio fora da lista, endereço privado e bucket errado devolvem `invalid_argument`. Objeto ausente devolve `not_found`. Falha de rede ou HTTP 5xx devolve `unavailable`. Resposta acima do limite devolve `quota_exceeded`.
5. **Auditoria.** O argumento `content_text` continua fora do evento de auditoria. A URI, o nome do arquivo e os demais argumentos entram no evento `mcp.tool_call`.

## Alternativas avaliadas

- **Permitir toda URL `https://` e confiar no cliente:** simples, mas transforma o servidor em um proxy para a rede interna. Recusado.
- **Baixar no cliente e enviar sempre o texto:** tira o risco do servidor, mas contradiz a seção 5.7 e impede o caso de uso de um bucket do tenant. Recusado.
- **Confiar só na lista de domínios, sem conferir o endereço resolvido:** um nome público pode apontar para `127.0.0.1`. Recusado.
- **Fixar o endereço resolvido na conexão HTTP:** elimina a troca de DNS entre a conferência e a requisição. Exige transporte próprio no cliente HTTP. Registrado como tratamento da limitação L23.

## Consequências

- O download por `https://` só funciona depois que o operador informa a lista de domínios.
- O cliente HTTP resolve o nome uma segunda vez. A limitação L23 registra a janela de troca de DNS.
- O tamanho do download respeita o menor valor entre `VLADE_SOURCES__MAX_BYTES` e `VLADE_LIMITS__MAX_UPLOAD_BYTES`.
- O teste unitário cobre a lista de domínios, o endereço privado, a porta, o redirecionamento, o limite de tamanho e a chave `s3://` de outro tenant.
