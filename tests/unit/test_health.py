import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from vlade_rag import __version__
from vlade_rag.api.app import create_app
from vlade_rag.core.config import Settings
from vlade_rag.native import backend


def test_health_live() -> None:
    client = TestClient(create_app(Settings()))
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "native_backend": backend(),
    }


def test_docs_disabled_in_prod() -> None:
    client = TestClient(create_app(Settings(environment="prod")))
    assert client.get("/docs").status_code == 404
