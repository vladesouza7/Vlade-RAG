# ADR-0010: Docling para extração de documentos

- Status: Aceito
- Data: 2026-11-19
- Decisão no VLADE-RAG.md: D6

## Contexto

O Vlade-RAG precisa extrair texto e estrutura de PDF e DOCX. O PyMuPDF é rápido, mas usa licença AGPL-3.0. O Docling usa licença MIT, preserva a estrutura (títulos, tabelas, páginas) e exporta Markdown.

## Decisão

1. O adapter padrão de `DocumentParser` para PDF e DOCX usa Docling, no extra `parsers`.
2. HTML usa BeautifulSoup. Texto puro e Markdown usam parsers próprios sem dependência externa.
3. O parser grava a página de origem de cada trecho quando o formato informa a página.
4. Um adapter PyMuPDF pode existir como extra opcional separado, com aviso de licença.

## Alternativas avaliadas

- **PyMuPDF:** rápido, mas AGPL-3.0.
- **pypdf:** licença BSD, mas perde a estrutura do documento.
- **Unstructured:** cobre muitos formatos, mas traz muitas dependências.

## Consequências

- O Docling usa modelos de layout e consome mais memória e CPU que um extrator simples. A configuração permite desligar a análise de layout para documentos simples.
- O benchmark de ingestão (RNF-04) mede o Docling.
