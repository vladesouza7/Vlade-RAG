"""Publish an answer evaluation report to Arize Phoenix as an experiment (ADR-0026).

The report is the JSON of ``vlade-rag eval answers``. Phoenix gets a dataset (the questions and
the expected answers), an experiment (the configuration of the run), one run per question (the
answer) and one evaluation per metric (the RAGAS scores and ``grounded``). The module uses the
REST API of Phoenix and the standard library only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from vlade_rag.core.domain import InvalidArgument, ProviderUnavailable

CODE_METRICS = {"grounded"}  # computed by the code; the others by an LLM judge


@dataclass(frozen=True, slots=True)
class PublishResult:
    dataset_id: str
    experiment_id: str
    runs: int
    evaluations: int
    skipped_questions: tuple[str, ...]
    url: str


class PhoenixClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def call(self, method: str, path: str, body: Any | None = None) -> Any:
        if not self.base_url.startswith(("http://", "https://")):
            raise InvalidArgument("The Phoenix address must start with http:// or https://.")
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 (checked)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ProviderUnavailable(
                f"Phoenix answered {exc.code} to {method} {path}: {detail}"
            ) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderUnavailable(f"Phoenix is not reachable at {self.base_url}.") from exc
        return json.loads(text) if text else None


def publish_report(
    client: PhoenixClient,
    report: Mapping[str, Any],
    *,
    dataset_name: str,
    experiment_name: str | None = None,
) -> PublishResult:
    details: Sequence[Mapping[str, Any]] = report.get("details") or []
    config: Mapping[str, Any] = report.get("config") or {}
    if config.get("evaluator") != "answers" or not details:
        raise InvalidArgument("The file is not a report of 'vlade-rag eval answers'.")
    dataset_id = _dataset(client, dataset_name, details)
    examples = client.call("GET", f"/v1/datasets/{dataset_id}/examples")["data"]["examples"]
    by_question = {e["input"].get("question"): e["id"] for e in examples}
    experiment = client.call(
        "POST",
        f"/v1/datasets/{dataset_id}/experiments",
        {
            "name": experiment_name or _default_name(config),
            "description": "vlade-rag eval answers",
            "metadata": _metadata(config, report.get("metrics") or {}),
            "repetitions": 1,
        },
    )["data"]
    started = _date(config.get("date"))
    runs = evaluations = 0
    skipped: list[str] = []
    for detail in details:
        example_id = by_question.get(detail["question"])
        if example_id is None:
            skipped.append(detail["question"])
            continue
        end = started + timedelta(seconds=float(detail.get("seconds") or 0))
        run = client.call(
            "POST",
            f"/v1/experiments/{experiment['id']}/runs",
            {
                "dataset_example_id": example_id,
                "output": {
                    "answer": detail.get("answer"),
                    "grounded": detail.get("grounded"),
                    "cited_documents": detail.get("cited_documents", []),
                    "context_documents": detail.get("context_documents", []),
                },
                "repetition_number": 1,
                "start_time": started.isoformat(),
                "end_time": end.isoformat(),
            },
        )["data"]
        runs += 1
        scores = {**(detail.get("scores") or {}), "grounded": float(bool(detail.get("grounded")))}
        for name, score in scores.items():
            if score is None:
                continue
            client.call(
                "POST",
                "/v1/experiment_evaluations",
                {
                    "experiment_run_id": run["id"],
                    "name": name,
                    "annotator_kind": "CODE" if name in CODE_METRICS else "LLM",
                    "start_time": started.isoformat(),
                    "end_time": end.isoformat(),
                    "result": {"score": float(score)},
                },
            )
            evaluations += 1
    url = f"{client.base_url}/datasets/{dataset_id}/compare?experimentId={experiment['id']}"
    return PublishResult(dataset_id, experiment["id"], runs, evaluations, tuple(skipped), url)


def _dataset(client: PhoenixClient, name: str, details: Sequence[Mapping[str, Any]]) -> str:
    """The id of the dataset ``name``. A new dataset gets the questions of the report."""
    found = client.call("GET", f"/v1/datasets?name={urllib.parse.quote(name)}")["data"]
    if found:
        return str(found[0]["id"])
    created = client.call(
        "POST",
        "/v1/datasets/upload?sync=true",
        {
            "action": "create",
            "name": name,
            "description": "Questions of a Vlade-RAG evaluation dataset",
            "inputs": [{"question": d["question"]} for d in details],
            "outputs": [{"expected_answer": d.get("expected_answer")} for d in details],
            "metadata": [{} for _ in details],
        },
    )
    return str(created["data"]["dataset_id"])


def _default_name(config: Mapping[str, Any]) -> str:
    kb = (config.get("knowledge_base") or {}).get("slug", "kb")
    retrieval = (config.get("knowledge_base_config") or {}).get("retrieval") or {}
    rerank = retrieval.get("rerank") or {}
    reranker = rerank.get("model") if rerank.get("enabled") else "no-rerank"
    return f"{kb} {'+'.join(retrieval.get('retrievers', []))} {reranker} {config.get('date', '')}"


def _metadata(config: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any]:
    kb_config = config.get("knowledge_base_config") or {}
    return {
        "vlade_rag_version": config.get("vlade_rag_version"),
        "knowledge_base": (config.get("knowledge_base") or {}).get("slug"),
        "retrieval": kb_config.get("retrieval"),
        "generation": kb_config.get("generation"),
        "orchestration": kb_config.get("orchestration"),
        "scorer": config.get("scorer"),
        "metrics": dict(metrics),
    }


def _date(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.fromisoformat("2000-01-01T00:00:00+00:00")
