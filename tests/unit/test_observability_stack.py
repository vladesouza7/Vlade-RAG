"""Structure of the observability stack of task 4.5 (ADR-0015).

The tests read the Compose file and the configuration files. They do not start Docker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose" / "docker-compose.yml"
OBSERVABILITY = ROOT / "deploy" / "observability"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return load_yaml(COMPOSE)


def test_the_stack_services_are_defined(compose: dict[str, Any]) -> None:
    services = compose["services"]
    expected = {
        "alloy",
        "prometheus",
        "loki",
        "tempo",
        "grafana",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
        "redis-exporter",
    }
    assert expected <= set(services)


@pytest.mark.parametrize(
    ("service", "profiles"),
    [
        ("alloy", ["staging", "prod"]),
        ("prometheus", ["prod"]),
        ("loki", ["prod"]),
        ("tempo", ["prod"]),
        ("grafana", ["prod"]),
        ("node-exporter", ["prod"]),
        ("cadvisor", ["prod"]),
        ("postgres-exporter", ["prod"]),
        ("redis-exporter", ["prod"]),
    ],
)
def test_each_service_runs_in_the_expected_profile(
    compose: dict[str, Any], service: str, profiles: list[str]
) -> None:
    assert compose["services"][service]["profiles"] == profiles


@pytest.mark.parametrize(
    "service",
    [
        "alloy",
        "prometheus",
        "loki",
        "tempo",
        "grafana",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
        "redis-exporter",
    ],
)
def test_each_service_has_a_memory_limit(compose: dict[str, Any], service: str) -> None:
    assert compose["services"][service]["mem_limit"]


@pytest.mark.parametrize(
    "service",
    [
        "alloy",
        "prometheus",
        "loki",
        "tempo",
        "grafana",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
        "redis-exporter",
    ],
)
def test_each_host_port_binds_to_loopback(compose: dict[str, Any], service: str) -> None:
    for mapping in compose["services"][service].get("ports", []):
        assert mapping.startswith("127.0.0.1:"), mapping


def test_alloy_receives_otlp_and_forwards_the_three_signals() -> None:
    text = (OBSERVABILITY / "alloy" / "config.alloy").read_text(encoding="utf-8")
    assert 'otelcol.receiver.otlp "vlade"' in text
    assert "0.0.0.0:4317" in text and "0.0.0.0:4318" in text
    assert 'prometheus.remote_write "vlade"' in text
    assert 'otelcol.exporter.otlp "tempo"' in text
    assert 'loki.source.docker "vlade"' in text
    assert "sys.env(" in text  # staging can point to external backends


def test_alloy_reads_the_docker_logs(compose: dict[str, Any]) -> None:
    volumes = compose["services"]["alloy"]["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in volumes
    assert "/var/lib/docker/containers:/var/lib/docker/containers:ro" in volumes
    assert "../observability/alloy:/etc/alloy:ro" in volumes


def test_the_api_sends_telemetry_to_alloy_by_default(compose: dict[str, Any]) -> None:
    env = compose["x-app-env"]
    assert env["VLADE_OTEL__ENDPOINT"] == "${VLADE_OTEL__ENDPOINT:-http://alloy:4318}"
    assert env["VLADE_OTEL__ENABLED"] == "${VLADE_OTEL__ENABLED:-false}"


def test_prometheus_scrapes_the_exporters_and_accepts_remote_write(
    compose: dict[str, Any],
) -> None:
    config = load_yaml(OBSERVABILITY / "prometheus" / "prometheus.yml")
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert {"prometheus", "alloy", "node", "cadvisor", "postgres", "valkey"} <= set(jobs)
    assert jobs["alloy"]["static_configs"][0]["targets"] == ["alloy:12345"]
    command = compose["services"]["prometheus"]["command"]
    assert "--web.enable-remote-write-receiver" in command


def test_loki_keeps_logs_for_seven_days() -> None:
    config = load_yaml(OBSERVABILITY / "loki" / "local-config.yaml")
    assert config["auth_enabled"] is False
    assert config["limits_config"]["retention_period"] == "168h"
    assert config["schema_config"]["configs"][0]["store"] == "tsdb"
    assert config["compactor"]["retention_enabled"] is True


def test_tempo_receives_otlp_and_uses_local_storage() -> None:
    config = load_yaml(OBSERVABILITY / "tempo" / "tempo.yml")
    receiver = config["distributor"]["receivers"]["otlp"]["protocols"]
    assert receiver["grpc"]["endpoint"] == "0.0.0.0:4317"
    assert receiver["http"]["endpoint"] == "0.0.0.0:4318"
    assert config["storage"]["trace"]["backend"] == "local"
    assert config["compactor"]["compaction"]["block_retention"] == "48h"


def test_grafana_has_the_three_datasources() -> None:
    config = load_yaml(
        OBSERVABILITY / "grafana" / "provisioning" / "datasources" / "datasources.yml"
    )
    sources = {source["uid"]: source for source in config["datasources"]}
    assert set(sources) == {"prometheus", "loki", "tempo"}
    assert sources["prometheus"]["url"] == "http://prometheus:9090"
    assert sources["loki"]["url"] == "http://loki:3100"
    assert sources["tempo"]["url"] == "http://tempo:3200"
    assert sources["tempo"]["jsonData"]["tracesToLogsV2"]["datasourceUid"] == "loki"


def test_grafana_provisions_the_dashboard_folder() -> None:
    config = load_yaml(OBSERVABILITY / "grafana" / "provisioning" / "dashboards" / "dashboards.yml")
    provider = config["providers"][0]
    assert provider["folder"] == "Vlade-RAG"
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"
    assert (OBSERVABILITY / "grafana" / "dashboards").is_dir()


def test_the_example_environment_has_the_grafana_password() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "GRAFANA_ADMIN_PASSWORD=" in text
    assert "PROMETHEUS_RETENTION=15d" in text
