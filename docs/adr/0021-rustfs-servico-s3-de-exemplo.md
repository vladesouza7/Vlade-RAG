# ADR-0021: RustFS é o serviço S3 de exemplo

- Status: Aceito
- Data: 2026-11-21
- Completa os itens 3 e 4 do ADR-0017
- Decisão no VLADE-RAG.md: D2

## Contexto

O ADR-0017 tirou o MinIO do exemplo de implantação e deixou dois candidatos: RustFS e SeaweedFS. A escolha esperava um teste do container com o contrato do port `ObjectStorage`.

Em 2026-11-21, o mantenedor considerou usar o MinIO de novo, com a imagem que a Chainguard publica. O mantenedor escolheu o RustFS. Os motivos do ADR-0017 continuam válidos: o repositório do MinIO está arquivado e não há imagem oficial.

O teste de 2026-11-21 com a imagem `rustfs/rustfs:1.0.6` deu este resultado:

- As 20 verificações do contrato do port passaram contra o container (`s3-live`, com `VLADE_TEST_S3_*`). As verificações incluem objetos binários, objeto vazio, exclusão de mais de 1000 chaves e isolamento entre tenants.
- A API do perfil `dev`, com `VLADE_OBJECT_STORAGE__BACKEND=s3`, criou o bucket quando iniciou, gravou o arquivo original e o texto normalizado sob o prefixo do tenant e respondeu a uma busca.
- O endpoint `/health` responde 200. O container usou cerca de 25 MB de memória sem carga.

## Decisão

1. O RustFS (Apache-2.0) é o serviço S3 de exemplo. O serviço `rustfs` do Compose usa a versão fixa `rustfs/rustfs:1.0.6`.
2. O serviço entra nos perfis `staging` e `prod` e no perfil novo `s3`. O perfil `s3` liga o serviço no notebook: `docker compose --profile dev --profile s3 up`.
3. O Compose não muda o backend padrão. A aplicação usa o RustFS só com `VLADE_OBJECT_STORAGE__BACKEND=s3` e `S3_ENDPOINT_URL=http://rustfs:9000`. As credenciais do RustFS são `S3_ACCESS_KEY_ID` e `S3_SECRET_ACCESS_KEY`. O container não inicia com uma credencial vazia.
4. A CI roda o contrato do port contra um container do RustFS no job Python.
5. O SeaweedFS continua compatível pelo adapter S3, mas não entra no Compose.

## Alternativas avaliadas

- **MinIO com a imagem da Chainguard:** a imagem recebe atualizações. Mas um terceiro mantém a imagem, o projeto original está arquivado e a licença é AGPL-3.0. Recusado pelo mantenedor.
- **SeaweedFS:** licença Apache-2.0 e projeto ativo. Exige mais configuração para um bucket S3 simples. Fica como alternativa sem teste.
- **Nenhum serviço no Compose:** o operador precisaria de um S3 externo para o perfil `staging`. Recusado.

## Consequências

- A tarefa 2.4 do roadmap está concluída, e a limitação L7 fecha.
- Uma versão nova do RustFS exige mudar a tag no Compose e na CI. A CI roda o contrato com a versão nova.
- O RustFS é um projeto novo (versão 1.0 em 2026). Um problema de compatibilidade aparece primeiro no contrato do port na CI.
