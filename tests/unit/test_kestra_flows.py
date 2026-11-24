"""Structure of the Kestra flows of task 4.1 (ADR-0011)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml

FLOWS = Path(__file__).parents[2] / "deploy" / "kestra" / "flows"
NAMES = ("ingest_batch", "sync_source", "reindex_knowledge_base", "evaluate_nightly", "backup")


def flow(name: str) -> dict[str, Any]:
    data = yaml.safe_load((FLOWS / f"{name}.yaml").read_text("utf-8"))
    assert isinstance(data, dict)
    return data


def text_of(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


@pytest.mark.parametrize("name", NAMES)
def test_every_flow_has_a_namespace_and_tasks(name: str) -> None:
    data = flow(name)
    assert data["id"] == name
    assert data["namespace"] == "vlade"
    assert data["description"].strip()
    assert data["tasks"]

    for task in data["tasks"]:
        assert task["id"] and task["type"]
        if task["type"].endswith(".python.Script"):
            ast.parse(task["script"])  # the embedded Python must compile
        if task["type"].endswith(".shell.Commands"):
            assert task["commands"]


@pytest.mark.parametrize(
    "name", ("ingest_batch", "sync_source", "reindex_knowledge_base", "evaluate_nightly")
)
def test_api_flows_use_the_service_key_and_no_direct_database_access(name: str) -> None:
    text = text_of(flow(name))
    assert "secrets.VLADE_API_KEY" in text
    assert "/v1/" in text
    assert "secrets.VLADE_BACKUP_DB_PASSWORD" not in text


def test_ingest_batch_takes_documents_as_json() -> None:
    inputs = {item["name"]: item for item in flow("ingest_batch")["inputs"]}
    assert inputs["knowledge_base"]["required"] is True
    assert inputs["documents"]["type"] == "STRING"
    text = text_of(flow("ingest_batch"))
    assert "/v1/knowledge-bases/" in text
    assert "multipart/form-data" in text
    assert "filename" in text


def test_sync_source_calls_the_connector_endpoint() -> None:
    data = flow("sync_source")
    script = data["tasks"][0]["script"]
    assert "/v1/knowledge-bases/" in script
    assert "/sources/" in script
    assert "/sync" in script
    trigger = data["triggers"][0]
    assert trigger["disabled"] is True
    inputs = {item["name"]: item for item in data["inputs"]}
    assert inputs["source"]["required"] is True
    assert inputs["knowledge_base"]["required"] is True


def test_reindex_previews_and_confirms() -> None:
    script = flow("reindex_knowledge_base")["tasks"][0]["script"]
    assert "/v1/knowledge-bases/" in script
    assert '"confirm": True' in script
    assert "preview" in script
    assert "/v1/jobs/" in script


def test_evaluate_nightly_uses_a_registered_dataset() -> None:
    data = flow("evaluate_nightly")
    script = data["tasks"][0]["script"]
    assert "/v1/evaluations" in script
    assert "/v1/jobs/" in script
    trigger = data["triggers"][0]
    assert trigger["cron"] == "0 3 * * *"
    assert trigger["disabled"] is True
    inputs = {item["name"]: item for item in data["inputs"]}
    assert inputs["dataset"]["required"] is True


def test_backup_dumps_the_database_and_copies_the_bucket() -> None:
    data = flow("backup")
    assert len(data["tasks"]) == 3
    commands = text_of(data).lower()
    assert "pg_dump" in commands
    assert "aws s3 cp" in commands
    assert "mc mirror" in commands
    assert "/v1/" not in commands
    assert data["triggers"][0]["disabled"] is True
