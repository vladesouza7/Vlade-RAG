# ADR-0006: Armazenamento de objetos pela API S3

- Status: Aceito
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D2

## Contexto

O Vlade-RAG guarda o arquivo original de cada versão de documento. O MinIO usa licença AGPL-3.0 e mudou a distribuição da edição comunitária em 2025.

## Decisão

1. O port `ObjectStorage` usa a API S3. Qualquer serviço compatível com S3 funciona.
2. O perfil `dev` usa o adapter de sistema de arquivos.
3. Os perfis `staging` e `prod` usam MinIO como exemplo de implantação.
4. Antes da fase 2, verifique a situação atual da distribuição do MinIO. Se a imagem oficial não estiver disponível, use uma alternativa compatível com S3, por exemplo SeaweedFS, Garage ou RustFS, e atualize este ADR.
5. As chaves dos objetos começam com `{tenant_id}/`.

## Alternativas avaliadas

- **Guardar o arquivo no PostgreSQL:** sem serviço extra, mas o banco cresce rápido e o backup fica lento.
- **Não guardar o original:** menos armazenamento, mas impede a reindexação no modo `full`.

## Consequências

- O MinIO é um serviço externo sem modificação. A licença AGPL-3.0 do MinIO não afeta o pacote MIT.
- Um provedor de nuvem S3 funciona sem mudança de código.
