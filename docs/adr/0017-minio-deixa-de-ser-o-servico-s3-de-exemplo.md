# ADR-0017: O MinIO deixa de ser o serviço S3 de exemplo

- Status: Aceito
- Data: 2026-11-20
- Substitui o item 3 do ADR-0006 e cumpre o item 4 do ADR-0006

## Contexto

O item 4 do ADR-0006 manda verificar a situação da distribuição do MinIO antes da fase 2. A verificação de 2026-11-20 mostra:

- O MinIO parou de distribuir imagens e binários da edição comunitária em outubro de 2025.
- O repositório entrou em modo de manutenção em dezembro de 2025 e foi arquivado em fevereiro de 2026. O repositório não recebe mais correções.
- A imagem `minio/minio` não existe mais no Docker Hub. A última versão publicada é de 2025-10-15.
- Uma fonte consultada lista vulnerabilidades conhecidas na última versão da edição comunitária.

Os serviços S3 compatíveis que avaliamos:

| Serviço | Licença | Situação em 2026-11-20 |
|---|---|---|
| RustFS | Apache-2.0 | Ativo. Versão 1.0.6 de 2026-11-15. Imagem no Docker Hub |
| SeaweedFS | Apache-2.0 | Ativo. Versão 4.54 de 2026-11-16. Imagem no Docker Hub |
| Garage | AGPL-3.0 | Ativo. Imagem no Docker Hub. Exige configuração de layout |
| MinIO | AGPL-3.0 | Repositório arquivado. Sem imagem oficial |

## Decisão

1. O Vlade-RAG não usa mais o MinIO como exemplo de implantação.
2. O adapter S3 não depende de um serviço. Ele usa o extra `s3` (`boto3`, Apache-2.0) e funciona com o AWS S3 e com qualquer serviço compatível. O contrato do port `ObjectStorage` roda contra o adapter em memória, contra o adapter de arquivos e contra o adapter S3 (com `moto`, um S3 em processo).
3. O serviço de exemplo dos perfis `staging` e `prod` será o RustFS ou o SeaweedFS. Os dois têm licença Apache-2.0. A escolha final espera o teste do container com o contrato do port (variáveis `VLADE_TEST_S3_*`).
4. Até a escolha, o Compose não traz um serviço S3. O operador aponta o Vlade-RAG para um S3 existente com as variáveis `S3_*`.
5. Um serviço com licença AGPL continua permitido como processo separado e sem modificação (ADR-0001). Ele não entra como exemplo.

## Alternativas avaliadas

- **Compilar o MinIO do código-fonte:** a licença AGPL não dá garantia, o repositório está arquivado e cada versão exige uma compilação própria. Recusado.
- **Imagens de terceiros do MinIO:** terceiros mantêm essas imagens e as condições de uso não foram verificadas. Recusado como padrão.
- **Guardar o arquivo no PostgreSQL:** o ADR-0006 já avaliou e recusou.

## Consequências

- A seção 17 do `ARCHITECTURE.md` lista um serviço S3 compatível no lugar do `minio`.
- A tarefa 2.4 do roadmap só termina quando o serviço de exemplo estiver validado.
- O pacote MIT continua sem dependência AGPL.
- Quem já tem um S3 (AWS, outro serviço compatível) usa o Vlade-RAG hoje, sem esperar o serviço de exemplo.
