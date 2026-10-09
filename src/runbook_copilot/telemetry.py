"""OpenTelemetry traces + metrics for the Copilot. Fully optional and a strict no-op when disabled.

Enable with OTEL_ENABLED=true and the standard OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://otel-lgtm:4318).
Install the extras:  pip install ".[otel]"

Signals
  traces : copilot.triage > copilot.retrieve | copilot.llm.generate | copilot.guardrails   (+ FastAPI server spans)
  metrics: copilot.requests, copilot.request.duration, copilot.retrieval.duration, copilot.llm.duration,
           copilot.retrieval.top_bm25, copilot.groundedness, copilot.parse.failures,
           copilot.guardrail.interventions, copilot.llm.tokens, copilot.llm.cost.usd
Every metric carries `environment` and `version` so dashboards can compare releases.
Question text is never attached to telemetry (only its length).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from .config import Settings, get_settings

try:  # the SDK is an optional extra
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra installed
    _OTEL_AVAILABLE = False

_LATENCY_BUCKETS = [0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]
_RATIO_BUCKETS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
_SCORE_BUCKETS = [2, 4, 8, 12, 16, 20, 25, 30, 40, 60]


class _NoopSpan:
    def set(self, **attrs: Any) -> None:
        pass


class _Span:
    def __init__(self, span):
        self._span = span

    def set(self, **attrs: Any) -> None:
        for k, v in attrs.items():
            if v is not None:
                self._span.set_attribute(k, v)


def _hist(meter, name: str, unit: str, desc: str, buckets: list[float]):
    try:
        return meter.create_histogram(name, unit=unit, description=desc, explicit_bucket_boundaries_advisory=buckets)
    except TypeError:  # older API without the advisory parameter
        return meter.create_histogram(name, unit=unit, description=desc)


class Telemetry:
    def __init__(self, settings: Settings | None = None, tracer_provider=None, meter_provider=None):
        s = settings or get_settings()
        self.enabled = bool(_OTEL_AVAILABLE and (tracer_provider or meter_provider))
        self.base = {"environment": s.app_env, "version": s.app_version}
        if not self.enabled:
            return
        self.tracer = (tracer_provider or otel_trace.get_tracer_provider()).get_tracer("runbook_copilot")
        meter = (meter_provider or otel_metrics.get_meter_provider()).get_meter("runbook_copilot")
        self.requests = meter.create_counter("copilot.requests", unit="{request}", description="Triage requests")
        self.duration = _hist(meter, "copilot.request.duration", "s", "End-to-end request latency", _LATENCY_BUCKETS)
        self.retrieval_duration = _hist(meter, "copilot.retrieval.duration", "s", "Retrieval + gate latency", _LATENCY_BUCKETS)
        self.llm_duration = _hist(meter, "copilot.llm.duration", "s", "LLM call latency incl. retries", _LATENCY_BUCKETS)
        self.top_bm25 = _hist(meter, "copilot.retrieval.top_bm25", "1", "Top BM25 score per request", _SCORE_BUCKETS)
        self.groundedness = _hist(meter, "copilot.groundedness", "1", "Lexical groundedness of evidence", _RATIO_BUCKETS)
        self.parse_failures = meter.create_counter("copilot.parse.failures", unit="{failure}", description="Unparseable model outputs")
        self.guardrail = meter.create_counter("copilot.guardrail.interventions", unit="{event}",
                                              description="Times a guardrail corrected the model output")
        self.tokens = meter.create_counter("copilot.llm.tokens", unit="{token}", description="LLM tokens")
        self.cost = meter.create_counter("copilot.llm.cost.usd", unit="1", description="Estimated LLM spend in USD")
        self.agent_runs = meter.create_counter("copilot.agent.runs", unit="{run}", description="Agent runs by outcome")
        self.agent_actions = meter.create_counter("copilot.agent.actions", unit="{action}",
                                                  description="Agent policy decisions and cluster writes")
        self.agent_duration = _hist(meter, "copilot.agent.duration", "s", "Agent run duration", _LATENCY_BUCKETS)

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Any]:
        if not self.enabled:
            yield _NoopSpan()
            return
        with self.tracer.start_as_current_span(name) as sp:
            handle = _Span(sp)
            handle.set(**attrs)
            yield handle

    def current_trace_id(self) -> str | None:
        if not self.enabled:
            return None
        ctx = otel_trace.get_current_span().get_span_context()
        return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None

    def record_agent(self, rep) -> None:
        """Emit metrics for one finished agent run (an AgentReport)."""
        if not self.enabled:
            return
        base = {**self.base, "agent_environment": rep.environment}
        self.agent_runs.add(1, {**base, "status": rep.status})
        self.agent_duration.record(rep.duration_s, base)
        for st in rep.steps:
            if st["kind"] == "policy":
                self.agent_actions.add(1, {**base, "action": st.get("action", ""), "decision": st["outcome"]})
            elif st["kind"] == "apply":
                self.agent_actions.add(1, {**base, "action": st.get("action", ""), "decision": "applied_ok" if st.get("ok") else "applied_failed"})
            elif st["kind"] == "rollback":
                self.agent_actions.add(1, {**base, "action": "rollback", "decision": "rolled_back"})

    def record_request(self, result) -> None:
        """Emit metrics for one finished request (a TriageResult)."""
        if not self.enabled:
            return
        r, t = result.response, result.trace
        self.requests.add(1, {**self.base, "found_answer": str(r.found_answer).lower(),
                              "incident_type": r.incident_type, "abstain_source": t.abstain_source or "none"})
        self.duration.record(t.latency_ms / 1000, self.base)
        self.retrieval_duration.record(t.retrieval_ms / 1000, self.base)
        self.top_bm25.record(t.top_bm25, self.base)
        if t.llm_ms:
            self.llm_duration.record(t.llm_ms / 1000, self.base)
        if t.groundedness is not None:
            self.groundedness.record(t.groundedness, self.base)
        if not t.parse_ok:
            self.parse_failures.add(1, self.base)
        for kind, n in (("command", len(t.dropped_commands)), ("citation", len(t.dropped_citations)),
                        ("remediation", t.flagged_remediation)):
            if n:
                self.guardrail.add(n, {**self.base, "kind": kind})
        if t.prompt_tokens:
            self.tokens.add(t.prompt_tokens, {**self.base, "type": "prompt"})
        if t.completion_tokens:
            self.tokens.add(t.completion_tokens, {**self.base, "type": "completion"})
        if t.cost_usd:
            self.cost.add(t.cost_usd, self.base)


_current = Telemetry()  # disabled by default


def get_telemetry() -> Telemetry:
    return _current


def setup_telemetry(settings: Settings | None = None) -> Telemetry:
    """Create exporters from the standard OTEL_* environment variables and install global providers."""
    global _current
    s = settings or get_settings()
    if not (s.otel_enabled and _OTEL_AVAILABLE):
        return _current
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": "runbook-copilot", "service.version": s.app_version,
                                "deployment.environment": s.app_env})
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    mp = MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())])
    otel_trace.set_tracer_provider(tp)
    otel_metrics.set_meter_provider(mp)
    _current = Telemetry(s, tracer_provider=tp, meter_provider=mp)
    return _current


def instrument_fastapi(app) -> None:
    """Server spans for every route except /health. No-op when telemetry is disabled."""
    if not _current.enabled:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
