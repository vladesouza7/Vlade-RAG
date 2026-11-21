"""Query flow engines (ARCHITECTURE 12.1). The linear pipeline is the default."""

from __future__ import annotations

from vlade_rag.core.application.answer import AnswerEngine, PipelineEngine


def answer_engines() -> dict[str, AnswerEngine]:
    """The engines this installation has. ``langgraph`` needs the extra of the same name."""
    engines: dict[str, AnswerEngine] = {"pipeline": PipelineEngine()}
    try:
        from vlade_rag.orchestration.langgraph import LangGraphEngine
    except ImportError:
        return engines
    engines["langgraph"] = LangGraphEngine()
    return engines
