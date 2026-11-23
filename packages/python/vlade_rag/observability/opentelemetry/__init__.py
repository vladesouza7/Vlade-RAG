"""OpenTelemetry adapters of the ``Tracer`` and ``Metrics`` ports (ADR-0015).

Needs the ``otel`` extra. ``setup_telemetry`` returns a no-op tracer when telemetry is disabled
or the SDK is missing, so the framework works without it. ``setup_metrics`` does the same for
metrics. The instruments use the catalogue in ARCHITECTURE section 16.2.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from vlade_rag.core.application import NoopMetrics, NoopTracer
from vlade_rag.core.config import Settings
from vlade_rag.core.ports import AttrValue, Metrics, Span, Tracer

INSTRUMENTATION = "vlade_rag"

# Estimated prices in USD per million tokens (input, output). The table is deliberately small:
# an unknown model reports zero cost instead of a guessed price. Update it when a provider
# changes its prices. The dashboards label the cost as an estimate.
_MODEL_PRICES: tuple[tuple[str, float, float], ...] = (
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.00),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("claude-3-5-sonnet", 3.00, 15.00),
    ("claude-3-7-sonnet", 3.00, 15.00),
    ("gemini-2.0-flash", 0.10, 0.40),
    ("gemini-2.5-flash", 0.30, 2.50),
    ("deepseek", 0.27, 1.10),
    ("llama-3.3-70b", 0.60, 0.60),
)

_METER_PROVIDER: Any = None


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


class OtelMetrics:
    """Record the metric catalogue with an OpenTelemetry meter.

    Instruments are created once, on first use. Counter names already end in ``_total``;
    the OTLP-to-Prometheus exporter does not add a second suffix.
    """

    def __init__(self, meter: Any | None = None) -> None:
        from opentelemetry import metrics

        self._meter = meter or metrics.get_meter(INSTRUMENTATION)
        self._instruments: dict[tuple[str, str], Any] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, AttrValue], ...]], float] = {}
        self._observables: set[str] = set()

    def _instrument(self, kind: str, name: str) -> Any:
        key = (kind, name)
        instrument = self._instruments.get(key)
        if instrument is None:
            if kind == "counter":
                instrument = self._meter.create_counter(name)
            elif kind == "histogram":
                # Only duration histograms carry a unit. A unit would rename the exported
                # metric (for example, vlade_retrieval_results -> ..._results_seconds).
                unit = "s" if name.endswith("_duration_seconds") else ""
                instrument = self._meter.create_histogram(name, unit=unit)
            else:
                instrument = self._meter.create_up_down_counter(name)
            self._instruments[key] = instrument
        return instrument

    def counter(
        self, name: str, value: float = 1, attributes: Mapping[str, AttrValue] | None = None
    ) -> None:
        self._instrument("counter", name).add(value, dict(attributes or {}))

    def histogram(
        self, name: str, value: float, attributes: Mapping[str, AttrValue] | None = None
    ) -> None:
        self._instrument("histogram", name).record(value, dict(attributes or {}))

    def gauge(
        self, name: str, value: float, attributes: Mapping[str, AttrValue] | None = None
    ) -> None:
        labels = tuple(sorted((attributes or {}).items()))
        self._gauges[(name, labels)] = value
        if name not in self._observables:
            # A gauge reports the last value at collection time. An UpDownCounter would add
            # deltas and drift away from the real queue depth.
            from opentelemetry.metrics import Observation

            def observe(options: Any) -> Any:
                for (metric_name, attrs), current in self._gauges.items():
                    if metric_name == name:
                        yield Observation(current, dict(attrs))

            self._meter.create_observable_gauge(name, callbacks=[observe])
            self._observables.add(name)

    def llm_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        labels = {"provider": provider, "model": model}
        self.counter("vlade_llm_tokens_total", input_tokens, {**labels, "direction": "input"})
        self.counter("vlade_llm_tokens_total", output_tokens, {**labels, "direction": "output"})
        needle = model.lower()
        input_price = output_price = 0.0
        for name, candidate_input, candidate_output in _MODEL_PRICES:
            if name in needle:
                input_price, output_price = candidate_input, candidate_output
                break
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        self.counter("vlade_llm_cost_usd_total", cost, labels)


def _meter_provider(settings: Settings) -> Any | None:
    if not settings.otel.enabled or not settings.otel.metrics:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        return None
    endpoint = settings.otel.endpoint
    url = f"{endpoint}/v1/metrics" if endpoint else None
    return MeterProvider(
        resource=Resource.create({"service.name": settings.otel.service_name}),
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=url))],
    )


def setup_telemetry(settings: Settings) -> Tracer:
    """Configure the global tracer and meter providers. Returns the tracer for the use cases."""
    if not settings.otel.enabled:
        return NoopTracer()
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_url)))
    trace.set_tracer_provider(provider)
    global _METER_PROVIDER
    _METER_PROVIDER = _meter_provider(settings)
    if _METER_PROVIDER is not None:
        from opentelemetry import metrics

        metrics.set_meter_provider(_METER_PROVIDER)
    return OtelTracer()


def setup_metrics(settings: Settings) -> Metrics:
    """Return the metrics adapter of the global meter configured by ``setup_telemetry``."""
    if not settings.otel.enabled or not settings.otel.metrics:
        return NoopMetrics()
    try:
        return OtelMetrics()
    except ImportError:
        return NoopMetrics()


def flush_telemetry(timeout_millis: int = 5000) -> None:
    """Send the spans and the metrics that wait in the batch before a short process ends."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    flush = getattr(trace.get_tracer_provider(), "force_flush", None)
    if flush is not None:
        flush(timeout_millis)
    if _METER_PROVIDER is not None:
        _METER_PROVIDER.force_flush(timeout_millis)


__all__ = ["OtelMetrics", "OtelTracer", "flush_telemetry", "setup_metrics", "setup_telemetry"]
