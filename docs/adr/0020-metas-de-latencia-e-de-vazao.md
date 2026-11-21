# ADR-0020: Metas de latência e de vazão depois do benchmark da fase 3

- Status: Proposto
- Data: 2026-11-21
- Decisão no VLADE-RAG.md: —

## Contexto

O critério de aceite da fase 3 diz: se uma meta de RNF-01 a RNF-04 falha, um ADR registra a meta nova ou o plano de correção. O benchmark da tarefa 3.10 mediu as quatro metas. Os dados e o método estão em `evals/reports/fase3-benchmark/README.md`.

| RNF | Meta | Medida |
|---|---|---|
| 01 | p95 de `search` sem reranker, 1 milhão de chunks, ≤ 300 ms | p95 de 812 ms na base pequena. Na base sintética, p95 de 408 ms com 6 mil chunks e 7,998 s com 104 mil. Sem teste com 1 milhão |
| 02 | p95 de `search` com reranker de 50 candidatos, ≤ 1 s | p95 de 1,978 s e 2,229 s, com dois rerankers por API |
| 03 | Primeiro token, sem o LLM remoto, ≤ 1,5 s | p95 de 591 ms só com a busca vetorial. p95 de 7,559 s com a configuração padrão. Base de 104 mil chunks |
| 04 | Ingestão por worker, sem embeddings, ≥ 50 páginas por segundo | De 8 a 70 páginas por segundo, conforme o tamanho do documento |

Os fatos que explicam os números:

- O embedding remoto da pergunta leva 787 ms no p95. O PostgreSQL leva de 13 a 21 ms.
- O reranker por API leva de 1,216 s a 1,435 s no p95, sozinho.
- A busca lexical custa de 43 a 76 µs de p95 por chunk. Ela classifica todos os chunks que casam com a pergunta.
- Cada documento custa 62 transações na ingestão. No perfil de documentos curtos, a reserva em Python do motor nativo pesa 1,9% do tempo de processamento.
- O índice HNSW de 104 mil chunks de 1.024 dimensões ocupou 627 MB.

O benchmark tem limites: uma máquina de 7,7 GB, um container de PostgreSQL de 1 GiB, base sintética e sem o motor Rust. Eles estão no relatório.

## Decisão proposta

Este ADR está em Status Proposto. O mantenedor decide. Até a aceitação, as metas do `PROJECT_SPEC.md` não mudam.

1. **RNF-04: manter a meta e definir o documento.** A meta de 50 páginas por segundo vale para documentos de cerca de 100 páginas. O texto do RNF-04 passa a dizer isso. O custo fixo de 62 transações por documento fica registrado como débito. O plano tem três partes. Gravar os passos do job em uma só transação. Agrupar as escritas de chunks e de embeddings. Evitar a leitura repetida do documento e da versão. Depois da correção, o benchmark roda de novo e fixa uma meta para documentos curtos.

2. **RNF-01: três mudanças.**
   - **Meta sem o provedor de embeddings.** O texto passa a dizer "sem o tempo do provedor de embeddings remoto", como o RNF-03 e o RNF-04 já dizem. O valor de 300 ms continua. O embedding da pergunta depende do provedor, e o cache de embeddings de consulta (7 dias) já existe.
   - **Plano para a busca lexical.** A busca lexical passa de 300 ms com poucos milhares de chunks. A tarefa 3.4 (BM25 com índice próprio) ganha este critério de aceite: o p95 da busca lexical com 100 mil chunks fica abaixo de 300 ms no mesmo benchmark. Antes disso, é preciso decidir se a busca lexical atual deve parar de classificar todos os chunks que casam.
   - **A base de 1 milhão de chunks continua sem teste.** Ela exige uma máquina com memória para os vetores e para o índice. Só os vetores de 1.024 dimensões de 1 milhão de chunks ocupam cerca de 4 GB. No teste, o índice HNSW ocupou cerca de 6 KB por chunk, o que dá cerca de 6 GB para 1 milhão. O benchmark deste ADR roda no perfil `staging` quando ele existir.

3. **RNF-02: mudar a meta.** Um reranker por API não cumpre 1 s: o reranker sozinho leva mais de 1,2 s no p95. A proposta é "≤ 2,5 s com reranker por API", uma margem de 12% sobre o pior p95 medido (2,229 s), e manter "≤ 1 s" para o reranker local. O reranker local ainda não tem medida, porque a máquina de desenvolvimento não roda modelos locais. A meta de 1 s fica sem prova até alguém medir o reranker local.

4. **RNF-03: manter a meta.** O primeiro token sai logo depois da busca, então o RNF-03 herda os números do RNF-01 e do RNF-02. Ele não precisa de meta própria nova. A busca lexical é o que o leva a 7,5 s com a configuração padrão.

5. **Memória do PostgreSQL.** O container de 1 GiB do Compose ficou em 87% de uso com 104 mil chunks. O guia de implantação (tarefa 4.7) deve dizer que a memória do PostgreSQL precisa comportar o índice HNSW da base ativa, com folga.

6. **As transformações de consulta com LLM ficam fora das metas.** A medida de 2026-11-21 deu p95 de 7,1 s a 10,8 s na base real, contra 812 ms sem transformação. A chamada ao LLM leva de 6,4 s a 9,2 s. Nenhuma meta de latência vale para uma busca com transformação, e o padrão continua `none` (limitação L13).

## Alternativas avaliadas

- **Não mudar nenhuma meta:** as metas de RNF-01 e de RNF-02 ficam sem como serem cumpridas com provedores remotos. Recusado.
- **Baixar todas as metas para o valor medido:** uma meta que só repete a medida não guia o projeto. A proposta muda só o RNF-02, onde o provedor impõe o limite.
- **Medir com o `k6`, como diz a especificação:** o `k6` mede a camada HTTP. Este benchmark mede a biblioteca em processo, para separar o tempo de cada etapa. O `k6` pode entrar depois para a API.
- **Instalar o motor Rust antes de medir o RNF-04:** no perfil de documentos curtos, o banco domina e a reserva em Python pesa 1,9%. A instalação não mudaria a conclusão sobre esses documentos. Ela pode elevar a vazão dos documentos longos, que não foi perfilada.

## Consequências

- Se o ADR for aceito, o `PROJECT_SPEC.md` muda em RNF-01, RNF-02 e RNF-04, e o `ROADMAP.md` registra isso.
- A tarefa 3.4 (BM25) deixa de ser só uma comparação de qualidade e passa a ser também a correção de uma meta que falha.
- A redução de transações do worker é código novo, fora da tarefa 3.10.
- Os números deste ADR vêm de uma máquina só. Outra máquina dá outros valores. O script `scripts/benchmarks/bench.py` repete a medida.
