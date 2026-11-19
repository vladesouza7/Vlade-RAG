"""Build the ``legal-ptbr`` evaluation dataset (ROADMAP task 1.21).

Source: original publication of two Brazilian federal laws, from the Chamber of Deputies site.
Texts of laws are not protected by copyright in Brazil (Lei 9.610/1998, art. 8, IV).

- LGPD: Lei 13.709/2018 (original text, without later amendments)
- CDC: Lei 8.078/1990 (original text, without later amendments)

Output: ``evals/datasets/legal-ptbr/`` with 100 Markdown documents (50 per law), ``manifest.json``
and ``questions.jsonl``. Each question names the article that answers it and a phrase that must
appear in that document; the script fails if the phrase is missing.

Usage: python3 scripts/datasets/build_legal_ptbr.py [--cache DIR]
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "datasets" / "legal-ptbr"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) vlade-rag-dataset-builder"
DOCS_PER_LAW = 50

LAWS = {
    "lgpd": {
        "name": "LGPD (Lei 13.709/2018)",
        "url": "https://www2.camara.leg.br/legin/fed/lei/2018/"
        "lei-13709-14-agosto-2018-787077-publicacaooriginal-156212-pl.html",
    },
    "cdc": {
        "name": "Código de Defesa do Consumidor (Lei 8.078/1990)",
        "url": "https://www2.camara.leg.br/legin/fed/lei/1990/"
        "lei-8078-11-setembro-1990-365086-publicacaooriginal-1-pl.html",
    },
}

# (law, article, question, expected answer, phrase that must appear in the relevant document)
QUESTIONS = [
    (
        "lgpd",
        5,
        "O que é dado pessoal sensível segundo a LGPD?",
        "Dado pessoal sobre origem racial ou étnica, convicção religiosa, opinião política, "
        "filiação a sindicato ou organização religiosa, filosófica ou política, dado referente à "
        "saúde ou à vida sexual, dado genético ou biométrico, quando vinculado a uma pessoa "
        "natural.",
        "origem racial ou étnica",
    ),
    (
        "lgpd",
        65,
        "Quando a LGPD entra em vigor?",
        "Após decorridos 18 meses de sua publicação oficial.",
        "18 (dezoito) meses",
    ),
    (
        "lgpd",
        52,
        "Qual é o valor máximo da multa simples prevista na LGPD?",
        "Até 2% do faturamento da empresa no Brasil no último exercício, limitada a "
        "R$ 50.000.000,00 por infração.",
        "50.000.000,00",
    ),
    (
        "lgpd",
        14,
        "Como deve ser feito o tratamento de dados pessoais de crianças?",
        "Com o consentimento específico e em destaque dado por pelo menos um dos pais ou pelo "
        "responsável legal.",
        "pelo menos um dos pais",
    ),
    (
        "lgpd",
        5,
        "Quem é o encarregado pelo tratamento de dados pessoais?",
        "A pessoa natural indicada pelo controlador que atua como canal de comunicação entre o "
        "controlador, os titulares e a autoridade nacional.",
        "canal de comunicação",
    ),
    (
        "lgpd",
        7,
        "Em quais hipóteses o tratamento de dados pessoais pode ser realizado?",
        "Mediante consentimento do titular, para cumprimento de obrigação legal, pela "
        "administração pública, para estudos por órgão de pesquisa, para execução de contrato, "
        "para exercício regular de direitos, para proteção da vida, para tutela da saúde, para "
        "legítimo interesse e para proteção do crédito.",
        "fornecimento de consentimento",
    ),
    (
        "lgpd",
        19,
        "Em quanto tempo o controlador deve fornecer a declaração completa pedida pelo titular?",
        "No prazo de até 15 dias contado do requerimento do titular.",
        "15 (quinze) dias",
    ),
    (
        "lgpd",
        48,
        "O que o controlador deve fazer quando ocorre um incidente de segurança?",
        "Comunicar à autoridade nacional e ao titular a ocorrência de incidente de segurança que "
        "possa acarretar risco ou dano relevante aos titulares.",
        "incidente de segurança",
    ),
    (
        "lgpd",
        2,
        "Quais são os fundamentos da disciplina da proteção de dados pessoais?",
        "O respeito à privacidade, a autodeterminação informativa, a liberdade de expressão, a "
        "inviolabilidade da intimidade, o desenvolvimento econômico e tecnológico, a livre "
        "iniciativa e os direitos humanos.",
        "autodeterminação informativa",
    ),
    (
        "lgpd",
        4,
        "A LGPD se aplica ao tratamento de dados feito para fins exclusivamente jornalísticos?",
        "Não. A lei não se aplica ao tratamento para fins exclusivamente "
        "jornalísticos e artísticos.",
        "jornalístico",
    ),
    (
        "cdc",
        49,
        "Qual é o prazo para desistir de uma compra feita fora do estabelecimento comercial?",
        "7 dias a contar da assinatura do contrato ou do recebimento do produto ou serviço.",
        "no prazo de 7 dias",
    ),
    (
        "cdc",
        26,
        "Qual é o prazo para reclamar de vícios aparentes em produtos duráveis?",
        "90 dias. Para produtos não duráveis, o prazo é de 30 dias.",
        "noventa dias",
    ),
    (
        "cdc",
        2,
        "Quem é considerado consumidor pelo CDC?",
        "Toda pessoa física ou jurídica que adquire ou utiliza produto ou serviço como "
        "destinatário final.",
        "destinatário final",
    ),
    (
        "cdc",
        18,
        "Em quanto tempo o fornecedor deve sanar o vício de um produto?",
        "No prazo máximo de 30 dias.",
        "trinta dias",
    ),
    (
        "cdc",
        42,
        "O que acontece quando o consumidor é cobrado em quantia indevida?",
        "Tem direito à repetição do indébito, por valor igual ao dobro do que pagou em excesso, "
        "com correção monetária e juros legais.",
        "dobro",
    ),
    (
        "cdc",
        43,
        "Por quanto tempo informações negativas podem ficar em cadastros de consumidores?",
        "Por no máximo cinco anos.",
        "cinco anos",
    ),
    (
        "cdc",
        27,
        "Qual é o prazo de prescrição para pedir reparação de danos causados por fato do produto?",
        "Cinco anos, contados do conhecimento do dano e de sua autoria.",
        "cinco anos",
    ),
    (
        "cdc",
        6,
        "Quais são os direitos básicos do consumidor?",
        "Entre outros: proteção da vida, saúde e segurança; educação sobre o consumo; informação "
        "adequada; proteção contra publicidade enganosa; prevenção e reparação de danos; acesso à "
        "justiça; facilitação da defesa.",
        "direitos básicos",
    ),
    (
        "cdc",
        39,
        "O fornecedor pode condicionar a venda de um produto à compra de outro?",
        "Não. Condicionar o fornecimento de produto ou serviço ao fornecimento de outro é prática "
        "abusiva.",
        "condicionar o fornecimento",
    ),
    (
        "cdc",
        3,
        "O que é fornecedor segundo o CDC?",
        "Toda pessoa física ou jurídica, pública ou privada, nacional ou estrangeira, que "
        "desenvolve atividades de produção, montagem, criação, construção, transformação, "
        "importação, exportação, distribuição ou comercialização de produtos ou prestação de "
        "serviços.",
        "Fornecedor é toda pessoa",
    ),
]

_ARTICLE = re.compile(r"^Art\. ?(\d+)")
_HEADING = re.compile(r"^(TÍTULO|CAPÍTULO|Seção|SEÇÃO)\b")


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("p", "br", "div", "h1", "h2", "h3", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def fetch(key: str, cache: Path | None) -> str:
    if cache is not None and (cache / f"{key}.html").exists():
        return (cache / f"{key}.html").read_text("utf-8")
    url = LAWS[key]["url"]  # fixed https URLs from LAWS
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URL
        html = response.read().decode("utf-8")
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{key}.html").write_text(html, "utf-8")
    return html


def lines_of(html: str) -> list[str]:
    parser = _Text()
    parser.feed(html)
    text = re.sub(r"[ \t\u00a0]+", " ", "".join(parser.parts))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = next(i for i, line in enumerate(lines) if line.startswith("Art. 1"))
    end = next(i for i, line in enumerate(lines) if line.startswith("Brasília,"))
    # keep the heading lines right before Art. 1
    while start > 0 and _HEADING.match(lines[start - 1]):
        start -= 1
    return lines[start:end]


def articles_of(lines: list[str]) -> list[tuple[int, str, str]]:
    """Return ``(number, heading context, text)`` for each article."""
    result: list[tuple[int, str, str]] = []
    headings: dict[str, str] = {}
    current: list[str] = []
    number = 0
    context = ""
    pending_heading = False
    for line in lines:
        heading = _HEADING.match(line)
        if heading:
            if number:
                result.append((number, context, "\n\n".join(current)))
                number, current = 0, []
            level = heading.group(1).upper()
            if level == "TÍTULO":
                headings = {"TÍTULO": line}
            elif level == "CAPÍTULO":
                headings = {k: v for k, v in headings.items() if k == "TÍTULO"}
                headings["CAPÍTULO"] = line
            else:
                headings["SEÇÃO"] = line
            pending_heading = True
            continue
        if pending_heading and not _ARTICLE.match(line):
            # heading title on the next line, for example "CAPÍTULO I" / "DISPOSIÇÕES GERAIS"
            last = list(headings)[-1]
            headings[last] = f"{headings[last]} — {line}"
            pending_heading = False
            continue
        pending_heading = False
        match = _ARTICLE.match(line)
        if match:
            if number:
                result.append((number, context, "\n\n".join(current)))
            number = int(match.group(1))
            context = " / ".join(headings.values())
            current = [line]
        elif number:
            current.append(line)
    if number:
        result.append((number, context, "\n\n".join(current)))
    return result


def groups(items: list[tuple[int, str, str]], count: int) -> list[list[tuple[int, str, str]]]:
    size, extra = divmod(len(items), count)
    out, start = [], 0
    for i in range(count):
        end = start + size + (1 if i < extra else 0)
        out.append(items[start:end])
        start = end
    return out


def build(cache: Path | None) -> None:
    docs_dir = OUT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for old in docs_dir.glob("*.md"):
        old.unlink()
    manifest: dict[str, dict[str, object]] = {}
    article_file: dict[tuple[str, int], str] = {}
    texts: dict[str, str] = {}
    for key, law in LAWS.items():
        articles = articles_of(lines_of(fetch(key, cache)))
        for index, group in enumerate(groups(articles, DOCS_PER_LAW), start=1):
            first, last = group[0][0], group[-1][0]
            span = f"Art. {first}" if first == last else f"Arts. {first} a {last}"
            name = f"{key}-{index:03d}.md"
            body = [f"# {law['name']} — {span}", ""]
            if group[0][1]:
                body += [f"_{group[0][1]}_", ""]
            body.append("\n\n".join(text for _, _, text in group))
            content = "\n".join(body).strip() + "\n"
            (docs_dir / name).write_text(content, "utf-8")
            texts[name] = content
            manifest[name] = {"law": key, "articles": [n for n, _, _ in group]}
            for number, _, _ in group:
                article_file[(key, number)] = name
    (OUT / "manifest.json").write_text(
        json.dumps(
            {"source": {k: v["url"] for k, v in LAWS.items()}, "documents": manifest},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    with (OUT / "questions.jsonl").open("w", encoding="utf-8") as out:
        for law, article, question, answer, phrase in QUESTIONS:
            name = article_file[(law, article)]
            if phrase.lower() not in texts[name].lower():
                raise SystemExit(f"Phrase {phrase!r} not found in {name} (Art. {article})")
            out.write(
                json.dumps(
                    {
                        "question": question,
                        "expected_answer": answer,
                        "relevant_documents": [name],
                        "law": law,
                        "article": article,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"{len(manifest)} documents, {len(QUESTIONS)} questions -> {OUT.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, help="Folder to cache the downloaded HTML pages.")
    build(parser.parse_args().cache)


if __name__ == "__main__":
    main()
