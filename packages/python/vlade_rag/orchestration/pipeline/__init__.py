"""Linear query pipeline in plain Python (default engine, ARCHITECTURE 12.1).

The engine lives in the core (``vlade_rag.core.application.answer``), so the use cases run without
any orchestration package. This module exposes it next to the LangGraph engine.
"""

from vlade_rag.core.application.answer import PipelineEngine

__all__ = ["PipelineEngine"]
