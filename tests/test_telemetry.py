import pytest

pytest.importorskip("opentelemetry.sdk")
from conftest import FakeLLM, good_answer  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,  # noqa: E402
)

from runbook_copilot.config import Settings  # noqa: E402
from runbook_copilot.llm.client import LLMReply  # noqa: E402
from runbook_copilot.pipeline import Copilot  # noqa: E402
from runbook_copilot.telemetry import Telemetry  # noqa: E402

Q = "my pod is in CrashLoopBackOff, what do I check?"


class UsageLLM:
    """Fake provider that reports token usage like the real client does."""

    def __init__(self, payload):
        self.payload = payload

    def __call__(self, messages):
        import json

        return LLMReply(json.dumps(self.payload), prompt_tokens=100, completion_tokens=50)


@pytest.fixture
def otel():
    spans = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    mp = MeterProvider(metric_readers=[reader])
    return spans, reader, tp, mp


def _metrics(reader):
    out = {}
    data = reader.get_metrics_data()
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                out[m.name] = m.data.data_points
    return out


def _settings(tmp_path, **kw):
    return Settings(log_path=tmp_path / "r.jsonl", min_bm25_score=0.5, min_query_coverage=0.3, llm_api_key="x",
                    app_env="test", app_version="v1", **kw)


def test_spans_metrics_tokens_and_cost(otel, retriever, tmp_path):
    spans, reader, tp, mp = otel
    s = _settings(tmp_path, price_in_per_1m=1.0, price_out_per_1m=2.0)
    cop = Copilot(retriever, UsageLLM(good_answer(diagnostic_commands=["kubectl get pods", "kubectl delete pod x"])), s,
                  log=False, telemetry=Telemetry(s, tp, mp))
    r = cop.triage(Q)

    names = {sp.name: sp for sp in spans.get_finished_spans()}
    assert {"copilot.triage", "copilot.retrieve", "copilot.llm.generate", "copilot.guardrails"} <= set(names)
    root = names["copilot.triage"]
    assert all(names[n].parent.span_id == root.context.span_id for n in
               ("copilot.retrieve", "copilot.llm.generate", "copilot.guardrails"))
    assert root.attributes["found_answer"] is True and root.attributes["environment"] == "test"
    assert root.attributes["version"] == "v1"
    # privacy: the question text itself must never be attached to telemetry
    assert all("CrashLoopBackOff, what" not in str(v) for sp in names.values() for v in sp.attributes.values())

    assert r.trace.prompt_tokens == 100 and r.trace.completion_tokens == 50
    assert r.trace.cost_usd == pytest.approx((100 * 1.0 + 50 * 2.0) / 1e6)
    assert r.trace.trace_id and len(r.trace.trace_id) == 32

    m = _metrics(reader)
    for name in ("copilot.requests", "copilot.request.duration", "copilot.retrieval.top_bm25", "copilot.llm.tokens",
                 "copilot.llm.cost.usd", "copilot.guardrail.interventions", "copilot.groundedness"):
        assert name in m, name
    tok = {dp.attributes["type"]: dp.value for dp in m["copilot.llm.tokens"]}
    assert tok == {"prompt": 100, "completion": 50}
    req = m["copilot.requests"][0]
    assert req.attributes["environment"] == "test" and req.attributes["found_answer"] == "true"
    guard = {dp.attributes["kind"]: dp.value for dp in m["copilot.guardrail.interventions"]}
    assert guard == {"command": 1}


def test_parse_failure_and_gate_abstain_metrics(otel, retriever, tmp_path):
    spans, reader, tp, mp = otel
    s = _settings(tmp_path)
    cop = Copilot(retriever, FakeLLM("garbage"), s, log=False, telemetry=Telemetry(s, tp, mp))
    cop.triage(Q)  # parse failure
    cop.triage("how do I make carbonara pasta")  # gate abstain, never reaches the LLM
    m = _metrics(reader)
    assert m["copilot.parse.failures"][0].value == 1
    sources = sorted(dp.attributes["abstain_source"] for dp in m["copilot.requests"])
    assert sources == ["gate", "parse_failure"]
    gate_spans = [sp for sp in spans.get_finished_spans() if sp.name == "copilot.triage"
                  and sp.attributes.get("abstain_source") == "gate"]
    assert gate_spans and not any(sp.name == "copilot.llm.generate" and sp.parent.span_id == gate_spans[0].context.span_id
                                  for sp in spans.get_finished_spans())


def test_disabled_is_a_noop(retriever, tmp_path):
    s = _settings(tmp_path)
    tel = Telemetry(s)
    assert tel.enabled is False and tel.current_trace_id() is None
    r = Copilot(retriever, FakeLLM(good_answer()), s, log=False, telemetry=tel).triage(Q)
    assert r.response.found_answer and r.trace.trace_id is None and r.trace.cost_usd is None


def test_cost_is_none_without_prices(retriever, tmp_path):
    s = _settings(tmp_path)
    r = Copilot(retriever, UsageLLM(good_answer()), s, log=False, telemetry=Telemetry(s)).triage(Q)
    assert r.trace.prompt_tokens == 100 and r.trace.cost_usd is None
