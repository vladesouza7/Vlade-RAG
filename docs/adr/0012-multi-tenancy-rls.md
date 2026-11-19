# ADR-0012: Isolamento de tenants com Row-Level Security

- Status: Aceito
- Data: 2026-11-19

## Contexto

O Vlade-RAG atende várias empresas no mesmo banco. Um vazamento de documento entre tenants é a falha mais grave possível do sistema.

## Decisão

1. Toda tabela com dados de cliente tem a coluna `tenant_id`.
2. Toda tabela com `tenant_id` usa RLS com `FORCE ROW LEVEL SECURITY`.
3. O adapter abre cada transação com `SET LOCAL app.tenant_id`.
4. O adapter também filtra por `tenant_id` em cada consulta. O RLS é a segunda barreira.
5. O papel da aplicação não é dono das tabelas e não tem `BYPASSRLS`.
6. O tenant vem sempre da credencial. Nenhum parâmetro de entrada define o tenant.
7. Um teste automatizado tenta ler dados de outro tenant por cada interface. Esse teste bloqueia a CI.

## Alternativas avaliadas

- **Um banco por tenant:** isolamento forte, mas a operação fica cara com muitos tenants.
- **Um schema por tenant:** isolamento bom, mas as migrações multiplicam.
- **Só filtro na aplicação:** simples, mas um erro de código vaza dados.

## Consequências

- Cada transação tem um custo pequeno extra de `SET LOCAL`.
- A autenticação usa um papel de banco separado (`vlade_auth`) para ler as chaves antes de existir um tenant na sessão.
- Um tenant com requisito de isolamento físico pode usar uma implantação própria.
