# ADR-0031: OIDC e OAuth 2.1 na API e no MCP

- Status: Aceito
- Data: 2026-11-23

## Contexto

A versão 1 autentica com chaves de API HMAC. A seção 3.2 do `MCP_SPEC.md` prevê OAuth 2.1 na fase 5, e o `VLADE-RAG.md` pede que os casos de uso não mudem quando essa autenticação entrar. API e MCP usam caminhos diferentes para ler o cabeçalho `Authorization`, mas os dois terminam em `TenantDirectory` e devolvem um `TenantContext`.

O projeto não tem provedor de identidade próprio. Um servidor deve poder aceitar tokens de um emissor externo sem mudar a API, o MCP nem os casos de uso.

## Decisão

1. **Helper único.** `authenticate_bearer` tenta primeiro a chave de API pelo port `TenantDirectory`. Se a chave falhar e o token tiver três partes separadas por ponto, ele verifica o JWT quando o OIDC está ligado. API e MCP chamam o mesmo helper.
2. **Verificação.** `OidcVerifier` usa PyJWT com o extra `oidc`. Ele lê a chave de assinatura do JWKS configurado, confere `iss`, `aud`, algoritmos e a presença de `exp`. A lista de algoritmos padrão contém só `RS256`.
3. **Claims.** O claim `tenant` traz o slug de um tenant existente. O claim `sub` identifica o principal. O claim `roles` traz os papéis `reader`, `writer` e `admin`. Um `sub` que não é UUID vira UUIDv5 determinístico a partir de `issuer:sub`. Sem papéis conhecidos, o contexto recebe só `reader`.
4. **Isolamento.** O tenant e os papéis vêm do token verificado. Nenhuma ferramenta MCP recebe `tenant_id` do cliente. A RLS do PostgreSQL continua como segunda barreira.
5. **Configuração.** OIDC começa desligado. `VLADE_AUTH__OIDC__ENABLED`, `__ISSUER`, `__AUDIENCE`, `__JWKS_URL`, `__ALGORITHMS`, `__TENANT_CLAIM` e `__ROLES_CLAIM` definem o emissor e a tradução de claims. Chaves de API continuam funcionando com OIDC ligado.
6. **Erros.** Token ausente, inválido, expirado, de emissor desconhecido ou com tenant inexistente devolve 401 na API e no MCP. O problema RFC 9457 e o cabeçalho `WWW-Authenticate: Bearer` permanecem.
7. **stdio.** O transporte stdio continua usando `VLADE_API_KEY` na inicialização. Ele não recebe um token por requisição.
8. **Testes.** `tests/unit/test_oidc.py` usa um par de chaves RSA locais. Testes de API e de MCP enviam um token assinado e conferem o contexto obtido.

## Alternativas avaliadas

- **Colocar a verificação dentro de `TenantDirectory`:** misturaria chave HMAC e JWT em um único método e exigiria mudanças nos dois adapters de tenant. Recusado.
- **Servidor de autorização próprio:** daria controle total, mas acrescentaria um serviço e armazenamento de segredos. Recusado.
- **Aceitar qualquer JWT sem conferir emissor e audiência:** permitiria que qualquer emissor emitisse tokens para o servidor. Recusado.
- **Biblioteca cliente OIDC completa:** traria dependências e fluxos de autorização que o servidor não precisa, pois ele só valida tokens de acesso. Recusado.

## Consequências

- A aplicação aceita dois tipos de credencial no mesmo cabeçalho. A detecção do JWT considera apenas a forma do token. A verificação decide a validade.
- O emissor precisa publicar um JWKS acessível ao servidor e incluir o tenant e os papéis como claims. O nome dos claims é configurável.
- Um token não é revogado pelo servidor. A validade depende de `exp`. Para revogar antes, o emissor precisa encurtar a validade ou trocar a chave de assinatura.
- O extra `oidc` acrescenta PyJWT e cryptography. As duas licenças atendem à ADR-0001.
