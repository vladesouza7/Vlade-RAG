"""The Agent Skill ``skills/vlade-rag`` (VLADE-RAG.md section 12.1, agentskills.io format)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parents[2] / "skills" / "vlade-rag"
SKILL = SKILL_DIR / "SKILL.md"


def parse(text: str) -> tuple[dict[str, str], str]:
    """Top-level ``key: value`` pairs of the YAML front matter, and the body."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.S)
    assert match, "SKILL.md must start with a YAML front matter between '---' lines"
    fields: dict[str, str] = {}
    for line in match[1].splitlines():
        if line and not line.startswith((" ", "\t")) and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields, match[2]


@pytest.fixture(scope="module")
def skill() -> tuple[dict[str, str], str]:
    return parse(SKILL.read_text(encoding="utf-8"))


def test_front_matter_follows_the_open_standard(skill: tuple[dict[str, str], str]) -> None:
    fields, _ = skill
    assert fields["name"] == SKILL_DIR.name == "vlade-rag"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"]) and len(fields["name"]) <= 64
    description = fields["description"]
    assert 50 <= len(description) <= 1024
    assert "Use quando" in description  # says when to use the skill
    assert fields["license"] == "MIT"
    assert len(fields.get("compatibility", "")) <= 500


def test_body_is_short_and_in_portuguese(skill: tuple[dict[str, str], str]) -> None:
    _, body = skill
    assert len(body.splitlines()) <= 500
    for heading in ("## Quando `grounded` é false", "## Erros", "## Regras"):
        assert heading in body


def test_skill_has_no_credentials_or_server_addresses(skill: tuple[dict[str, str], str]) -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert not re.search(r"https?://", text), "no fixed server address"
    assert not re.search(r"vrag_[A-Za-z0-9]", text), "no API key"
    assert not re.search(r"(?i)bearer\s+\S", text)
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), "no IP address"


def test_every_tool_the_skill_names_exists_on_the_server(
    skill: tuple[dict[str, str], str],
) -> None:
    pytest.importorskip("mcp")
    from vlade_rag.mcp.prompts import ANSWER, SUMMARIZE
    from vlade_rag.mcp.tools import read_tools

    tools = {t.name for t in read_tools()}
    _, body = skill
    named = set(re.findall(r"\bvlade_[a-z_]+\b", body))
    assert named <= tools | {ANSWER, SUMMARIZE}, named - tools
    # The skill teaches every read tool.
    assert tools <= named, tools - named


def test_error_codes_of_the_skill_are_the_server_codes(
    skill: tuple[dict[str, str], str],
) -> None:
    pytest.importorskip("mcp")
    from vlade_rag.mcp.policies import _KNOWN

    _, body = skill
    section = body.split("## Erros", 1)[1].split("##", 1)[0]
    codes: set[str] = set()
    for line in section.splitlines():
        if line.startswith("| `"):  # a table row: the first cell lists the codes
            codes |= set(re.findall(r"`([a-z_]+)`", line.split("|")[1]))
    assert codes <= _KNOWN, codes - _KNOWN
    for code in ("invalid_argument", "not_found", "forbidden", "rate_limited", "quota_exceeded"):
        assert code in codes
