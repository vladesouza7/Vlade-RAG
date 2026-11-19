import builtins
from typing import Any

import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner

from vlade_rag import __version__
from vlade_rag.cli import main
from vlade_rag.cli.app import app
from vlade_rag.native import backend

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"vlade-rag {__version__} backend={backend()}" in result.stdout


def test_api_serve_uses_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("uvicorn")
    import uvicorn

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setenv("VLADE_API__PORT", "8123")
    from vlade_rag.core.config import get_settings

    get_settings.cache_clear()
    try:
        result = runner.invoke(app, ["api", "serve", "--host", "127.0.0.2"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert calls == [{"factory": True, "host": "127.0.0.2", "port": 8123, "log_level": "info"}]


def test_main_without_cli_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "vlade_rag.cli.app":
            raise ImportError("No module named 'typer'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
