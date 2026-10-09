"""Generate observability/dashboards/copilot.json (Grafana, importable). Keeping panels in code makes review easy.

Metric names assume the standard OTel -> Prometheus translation (dots to underscores, unit suffix for 's',
_total for counters). If your collector uses a different translation strategy, adjust the names below and re-run.
"""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "${datasource}"}
F = 'environment=~"$environment",version=~"$version"'
_id = 0


def panel(title, exprs, kind="timeseries", x=0, y=0, w=12, h=8, unit=None, desc=None):
    global _id
    _id += 1
    p = {"id": _id, "type": kind, "title": title, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": lg, "datasource": DS} for i, (e, lg) in enumerate(exprs)],
         "fieldConfig": {"defaults": {"unit": unit} if unit else {}, "overrides": []}}
    if desc:
        p["description"] = desc
    return p


def q(metric, fn="rate", win="5m", extra=""):
    return f"{fn}({metric}{{{F}{extra}}}[{win}])"


req = "copilot_requests_total"
NOT_FOUND = ',found_answer="false"'  # label matcher, kept out of the f-strings (py3.10 compatible)
dur = "copilot_request_duration_seconds_bucket"
panels = [
    panel("Requests / s by version", [(f"sum by (version) ({q(req)})", "{{version}}")], x=0, y=0, unit="reqps"),
    panel("Latency p50 / p95", [
        (f"histogram_quantile(0.5, sum by (le) ({q(dur)}))", "p50"),
        (f"histogram_quantile(0.95, sum by (le) ({q(dur)}))", "p95")], x=12, y=0, unit="s"),
    panel("Abstain ratio", [(f'sum({q(req, extra=NOT_FOUND)}) / sum({q(req)})', "abstain ratio")],
          x=0, y=8, unit="percentunit", desc="Share of requests that returned found_answer=false. Compare versions after a release."),
    panel("Abstentions by source", [(f'sum by (abstain_source) ({q(req, extra=NOT_FOUND)})', "{{abstain_source}}")],
          x=12, y=8, desc="gate = retrieval gate, llm = model abstained, low_confidence, no_valid_citations, parse_failure"),
    panel("Parse failures (15m)", [(f"sum(increase(copilot_parse_failures_total{{{F}}}[15m]))", "failures")], kind="stat", x=0, y=16, w=6, h=5),
    panel("Guardrail interventions by kind", [(f"sum by (kind) ({q('copilot_guardrail_interventions_total')})", "{{kind}}")],
          x=6, y=16, w=9, h=5, desc="Times the model had to be corrected: command (not read-only), citation (not retrieved), remediation (write action flagged)."),
    panel("LLM cost (range)", [(f"sum(increase(copilot_llm_cost_usd_total{{{F}}}[$__range]))", "USD")], kind="stat", x=15, y=16, w=9, h=5,
          unit="currencyUSD", desc="Needs LLM_PRICE_IN_PER_1M / LLM_PRICE_OUT_PER_1M to be set."),
    panel("Retrieval top BM25 (p50)", [(f"histogram_quantile(0.5, sum by (le) ({q('copilot_retrieval_top_bm25_bucket')}))", "p50")], x=0, y=21),
    panel("Groundedness (p50)", [(f"histogram_quantile(0.5, sum by (le) ({q('copilot_groundedness_bucket')}))", "p50")], x=12, y=21, unit="percentunit"),
    panel("Tokens by type", [(f"sum by (type) ({q('copilot_llm_tokens_total')})", "{{type}}")], x=0, y=29, unit="short"),
    panel("LLM latency p95", [(f"histogram_quantile(0.95, sum by (le) ({q('copilot_llm_duration_seconds_bucket')}))", "p95")], x=12, y=29, unit="s"),
]


def var(name, query, label):
    return {"name": name, "label": label, "type": "query", "datasource": DS, "includeAll": True, "multi": True,
            "allValue": ".*", "refresh": 2, "query": {"query": query, "refId": name}, "current": {"text": "All", "value": "$__all"}}


dashboard = {
    "__inputs": [{"name": "DS_PROMETHEUS", "label": "Prometheus", "type": "datasource", "pluginId": "prometheus", "pluginName": "Prometheus"}],
    "title": "Runbook Copilot", "uid": "runbook-copilot", "schemaVersion": 39, "version": 1, "refresh": "30s",
    "time": {"from": "now-3h", "to": "now"}, "tags": ["runbook-copilot", "llm"],
    "templating": {"list": [
        {"name": "datasource", "label": "Data source", "type": "datasource", "query": "prometheus", "current": {}},
        var("environment", "label_values(copilot_requests_total, environment)", "Environment"),
        var("version", "label_values(copilot_requests_total, version)", "Version"),
    ]},
    "panels": panels,
}

if __name__ == "__main__":
    out = Path(__file__).parent / "dashboards" / "copilot.json"
    out.write_text(json.dumps(dashboard, indent=2) + "\n")
    print(f"wrote {out} ({len(panels)} panels)")
