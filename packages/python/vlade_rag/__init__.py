"""Vlade-RAG: modular, extensible Retrieval-Augmented Generation framework."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("vlade-rag")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

__all__ = ["__version__"]
