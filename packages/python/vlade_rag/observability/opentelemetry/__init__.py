"""OpenTelemetry adapter of the ``Tracer`` port and telemetry setup (ADR-0015).

Needs the ``otel`` extra. ``setup_telemetry`` returns a no-op tracer when telemetry is disabled
or the SDK is missing, so the framework works without it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from vlade_rag.core.application import NoopTracer
from vlade_rag.core.config import Settings
from vlade_rag.core.ports import AttrValue, Span, Tracer

INSTRUMENTATION = "vlade_rag"


class _OtelSpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: AttrValue) -> None:
        self._span.set_attribute(key, value)

    def add_event(self, name: str, attributes: Mapping[str, AttrValue] | None = None) -> None:
        self._span.add_event(name, dict(attributes or {}))


class OtelTracer:
    def __init__(self, tracer: Any | None = None) -> None:
        from opentelemetry import trace

        self._trace = trace
        self._tracer = tracer or trace.get_tracer(INSTRUMENTATION)

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, AttrValue] | None = None) -> Iterator[Span]:
        with self._tracer.start_as_current_span(name, attributes=dict(attributes or {})) as span:
            yield _OtelSpan(span)

    def current_trace_id(self) -> str | None:
        ctx = self._trace.get_current_span().get_span_context()
        return f"{ctx.trace_id:032x}" if ctx.is_valid else None


def setup_telemetry(settings: Settings) -> Tracer:
    """Configure the global tracer and meter providers. Returns the tracer for the use cases."""
    if not settings.otel.enabled:
        return NoopTracer()
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return NoopTracer()

    from vlade_rag import __version__

    resource = Resource.create(
        {
            "service.name": settings.otel.service_name,
            "service.version": __version__,
            "deployment.environment": settings.environment,
            "openinference.project.name": settings.otel.project,
        }
    )
    endpoint = settings.otel.endpoint
    traces_url = f"{endpoint}/v1/traces" if endpoint else None  # None: OTEL_EXPORTER_* env vars
    metrics_url = f"{endpoint}/v1/metrics" if endpoint else None
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_url)))
    trace.set_tracer_provider(provider)
    if settings.otel.metrics:
        reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=metrics_url))
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    return OtelTracer()


def flush_telemetry(timeout_millis: int = 5000) -> None:
    """Send the spans that wait in the batch. A short process (the CLI) calls it before it ends:
    without it, the process can end before the batch leaves."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    flush = getattr(trace.get_tracer_provider(), "force_flush", None)
    if flush is not None:
        flush(timeout_millis)


__all__ = ["OtelTracer", "flush_telemetry", "setup_telemetry"]
