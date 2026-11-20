"""MCP prompts (docs/MCP_SPEC.md section 7)."""

from __future__ import annotations

from collections.abc import Mapping

from mcp_types import GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent

from vlade_rag.core.domain import InvalidArgument

ANSWER = "vlade_answer_with_citations"
SUMMARIZE = "vlade_summarize_document"

_ARGUMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    ANSWER: (
        ("knowledge_base", "Slug da base de conhecimento."),
        ("question", "Pergunta do usuário."),
    ),
    SUMMARIZE: (
        ("knowledge_base", "Slug da base de conhecimento."),
        ("document_id", "Identificador do documento."),
    ),
}

_DESCRIPTIONS = {
    ANSWER: "Responde a uma pergunta só com as fontes da base e cita cada fonte.",
    SUMMARIZE: "Resume um documento da base e cita as páginas.",
}


def list_prompts() -> list[Prompt]:
    return [
        Prompt(
            name=name,
            description=_DESCRIPTIONS[name],
            arguments=[
                PromptArgument(name=arg, description=text, required=True) for arg, text in args
            ],
        )
        for name, args in _ARGUMENTS.items()
    ]


def get_prompt(name: str, arguments: Mapping[str, str] | None) -> GetPromptResult:
    """Build the messages of a prompt. Raises ``InvalidArgument`` for a missing argument."""
    wanted = _ARGUMENTS.get(name)
    if wanted is None:
        raise InvalidArgument(f"The prompt '{name}' does not exist.")
    values = dict(arguments or {})
    missing = [arg for arg, _ in wanted if not str(values.get(arg, "")).strip()]
    if missing:
        raise InvalidArgument(f"Missing argument: {', '.join(missing)}.")
    if name == ANSWER:
        text = (
            f"Chame a ferramenta `vlade_search` na base `{values['knowledge_base']}` para "
            f"encontrar fontes sobre esta pergunta: {values['question']}\n\n"
            "Responda só com informação das fontes. Cite cada fonte no formato [n]. "
            "Se as fontes não respondem à pergunta, diga que não encontrou a informação. "
            "Não complete a resposta com conhecimento próprio."
        )
    else:
        text = (
            f"Leia o documento `{values['document_id']}` da base `{values['knowledge_base']}` "
            "com a ferramenta `vlade_get_document` (use `include_text: true`). "
            "Resuma o documento. Cite a página de cada afirmação, quando a página existir. "
            "Se o texto vem cortado (`truncated: true`), avise o usuário."
        )
    return GetPromptResult(
        description=_DESCRIPTIONS[name],
        messages=[PromptMessage(role="user", content=TextContent(type="text", text=text))],
    )
