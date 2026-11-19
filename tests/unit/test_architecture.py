"""Enforce the dependency rule of ADR-0002 with a static import scan.

- ``vlade_rag.core`` imports only the standard library, pydantic, pydantic-settings
  and other ``vlade_rag.core`` modules.
- ``vlade_rag.core.domain`` imports only the standard library, pydantic and
  ``vlade_rag.core.domain``.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

import vlade_rag

PACKAGE_ROOT = Path(vlade_rag.__file__).parent
STDLIB = set(sys.stdlib_module_names) | {"__future__"}

CORE_ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_settings", "typing_extensions"}


def _imports(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def _violations(subpackage: str, allowed_internal: str, allowed_third_party: set[str]) -> list[str]:
    found = []
    for path in sorted((PACKAGE_ROOT / subpackage).rglob("*.py")):
        for name in _imports(path):
            top = name.split(".")[0]
            if top in STDLIB or top in allowed_third_party:
                continue
            if name == allowed_internal or name.startswith(allowed_internal + "."):
                continue
            found.append(f"{path.relative_to(PACKAGE_ROOT)} imports {name}")
    return found


def test_core_does_not_import_outer_layers() -> None:
    assert _violations("core", "vlade_rag.core", CORE_ALLOWED_THIRD_PARTY) == []


def test_domain_is_pure() -> None:
    assert _violations("core/domain", "vlade_rag.core.domain", {"pydantic"}) == []
