"""Structure of the documentation site (task 5.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "mkdocs.yml"


def config() -> dict[str, Any]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_site_uses_the_repository_docs() -> None:
    data = config()
    assert data["docs_dir"] == "docs"
    assert data["site_dir"] == "site"
    assert data["theme"]["name"] == "material"
    assert data["theme"]["language"] == "pt-BR"
    assert (ROOT / data["docs_dir"] / "index.md").is_file()


def test_landing_page_links_to_the_main_documents() -> None:
    text = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    for name in ("PROJECT_SPEC.md", "ARCHITECTURE.md", "MCP_SPEC.md", "ROADMAP.md"):
        assert name in text


def test_search_plugin_is_enabled() -> None:
    plugins = config()["plugins"]
    assert any((plugin == "search" or plugin.get("search") is not None) for plugin in plugins)
