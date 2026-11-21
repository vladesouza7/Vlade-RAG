"""Derive two harder variants of the ``legal-ptbr`` questions (ROADMAP tasks 3.2 and 3.3).

The 20 questions of ``questions.jsonl`` use the words of the law, so exact search already finds the
right document (Recall@10 of 1.00). Two variants keep the same relevant documents and change only
the question:

- ``questions-typos.jsonl``: two long words of each question get two inner letters swapped. The
  rule is fixed, so the file is the same on every run. It tests the fuzzy retriever.
- ``questions-paraphrase.jsonl``: everyday wording, written by hand, that avoids the key terms of
  the law. It tests query rewriting, multi-query and HyDE.

Usage: python3 scripts/datasets/derive_legal_ptbr_variants.py
Standard library only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATASET = Path(__file__).resolve().parents[2] / "evals" / "datasets" / "legal-ptbr"

# One paraphrase per question of questions.jsonl, in the same order. The relevant documents do not
# change: each paraphrase asks for the same information as the original question.
PARAPHRASES = [
    "Que tipo de informação sobre uma pessoa a lei de proteção de dados trata como mais delicada?",
    "A partir de que data essa lei de proteção de dados começou a valer?",
    "Até quanto a autoridade pode cobrar em dinheiro de uma empresa que descumpre a lei de dados?",
    "Quais cuidados uma empresa precisa ter ao usar informações de menores de idade?",
    "Quem faz a ponte entre a empresa, as pessoas e a autoridade nacional na proteção de dados?",
    "Em que situações é permitido usar as informações pessoais de alguém?",
    "Qual é o tempo máximo para a empresa entregar ao titular tudo o que guarda sobre ele?",
    "Se vazarem dados de clientes, o que a empresa tem que fazer?",
    "Em quais bases se apoia a proteção de dados no Brasil?",
    "A lei de dados vale para quem usa informações só para fazer reportagem?",
    "Posso me arrepender de uma compra feita pela internet? Em quantos dias?",
    "Até quando posso reclamar de um defeito visível em um eletrodoméstico?",
    "Quem a lei do consumidor considera como o destinatário final de um produto?",
    "Quanto tempo a loja tem para consertar um produto com defeito?",
    "Fui cobrado por uma dívida que não devia. Tenho direito a receber de volta?",
    "Por quantos anos meu nome pode ficar sujo em lista de maus pagadores?",
    "Quanto tempo tenho para pedir indenização por um dano causado por um produto defeituoso?",
    "Quais direitos fundamentais todo comprador tem?",
    "A loja pode exigir que eu leve outro item para me vender o que quero?",
    "Quem a lei considera como vendedor ou prestador de serviço?",
]

_WORD = re.compile(r"[^\W\d_]{7,}")


def swap_inside(word: str) -> str:
    """Swap two neighbouring letters in the middle of the word. Pick the first pair that differs."""
    middle = len(word) // 2
    for i in (middle, middle - 1, middle + 1, middle - 2):
        if word[i] != word[i + 1]:
            return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    return word


def add_typos(question: str) -> str:
    """Swap letters in the two longest words of 7 letters or more."""
    words = sorted(set(_WORD.findall(question)), key=lambda w: (-len(w), w))[:2]
    for word in words:
        question = question.replace(word, swap_inside(word))
    return question


def main() -> None:
    lines = (DATASET / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    items = [json.loads(line) for line in lines if line.strip()]
    if len(items) != len(PARAPHRASES):
        raise SystemExit(f"{len(items)} questions and {len(PARAPHRASES)} paraphrases.")
    variants = {
        "questions-typos.jsonl": [add_typos(item["question"]) for item in items],
        "questions-paraphrase.jsonl": PARAPHRASES,
    }
    for name, questions in variants.items():
        pairs = zip(items, questions, strict=True)
        rows = [{**item, "question": question} for item, question in pairs]
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        (DATASET / name).write_text(text, encoding="utf-8")
        print(f"{name}: {len(rows)} questions")


if __name__ == "__main__":
    main()
