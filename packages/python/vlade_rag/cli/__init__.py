"""Command-line interface. Install with the ``cli`` extra."""

from __future__ import annotations

import sys


def main() -> None:
    """Entry point of the ``vlade-rag`` command."""
    try:
        from vlade_rag.cli.main import app
    except ImportError as exc:
        sys.stderr.write(
            f'The vlade-rag CLI needs the "cli" extra: pip install "vlade-rag[cli]" ({exc})\n'
        )
        raise SystemExit(1) from exc
    app()
