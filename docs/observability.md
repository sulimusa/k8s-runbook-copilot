# Observability

The Copilot emits OpenTelemetry traces and metrics (OTLP over HTTP). Telemetry is **off by default** and a strict no-op
unless `OTEL_ENABLED=true` and the standard `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Every signal carries
`environment` and `version`, so a dashboard can compare releases side by side.

## Signals
| Kind | Name | Notes |
|---|---|---|
| trace | `copilot.triage` | root span; attributes `found_answer`, `incident_type`, `abstain_source`, `confidence`, `top_bm25`, `parse_attempts`, token counts |
| trace | `copilot.retrieve` / `copilot.llm.generate` / `copilot.guardrails` | child spans; guardrails span records dropped commands, dropped citations, flagged remediation, groundedness |
| trace | FastAPI server spans | every route except `/health` |
| metric | `copilot.requests` | counter by `found_answer`, `incident_type`, `abstain_source` |
| metric | `copilot.request.duration`, `copilot.retrieval.duration`, `copilot.llm.duration` | latency histograms (seconds) |
| metric | `copilot.retrieval.top_bm25`, `copilot.groundedness` | quality signals as histograms |
| metric | `copilot.parse.failures`, `copilot.guardrail.interventions{kind}` | reliability and "model needed correcting" |
| metric | `copilot.llm.tokens{type}`, `copilot.llm.cost.usd` | cost needs `LLM_PRICE_IN_PER_1M` / `LLM_PRICE_OUT_PER_1M` (copied from your provider's pricing page; never hard-coded) |

Logs: one JSON line per request in `logs/requests.jsonl` (`/stats` summarises it). Each line includes `trace_id`, so you can jump from a log line to the trace.

**Privacy:** question text is never attached to spans or metrics (only its length). Logs hash it unless `LOG_QUESTIONS=true`.

## Run it locally
```bash
cp .env.example .env            # add LLM_API_KEY
docker compose up --build       # Copilot :8000, Grafana :3000 (Grafana's all-in-one otel-lgtm image)
curl -s localhost:8000/triage -H 'content-type: application/json' -d '{"question":"pod in CrashLoopBackOff, why?"}'
```
Then in Grafana: *Dashboards > Import > `observability/dashboards/copilot.json`*, pick the Prometheus data source.
Traces are in Explore > Tempo (search `service.name=runbook-copilot`).

On the kind lab (`make platform-up`) the same backend runs in the `observability` namespace and `dev`/`prod` export to it.

## Dashboard and alerts
`observability/build_dashboard.py` generates the dashboard (11 panels: request rate by version, latency p50/p95, abstain ratio,
abstentions by source, parse failures, guardrail interventions, cost, retrieval score, groundedness, tokens, LLM latency).
`observability/alerts/copilot-rules.yaml` defines four alerts. Each names service, environment, version, owner, dashboard and runbook.

> **Status:** the instrumentation is unit-tested (spans, parent/child structure, metric values, token and cost maths, privacy).
> The compose stack, dashboard and alert rules were **not run against live data** in the environment where they were written.
> Dashboard queries assume the standard OTel to Prometheus name translation (`copilot_request_duration_seconds_bucket`,
> `copilot_requests_total`, ...). If a panel is empty, check the metric names in Grafana Explore and adjust `build_dashboard.py`.

## Alert runbooks
### Parse failures high
More than 5% of LLM responses fail schema validation. The pipeline abstains safely, but users get no answers.
1. Compare `version` on the dashboard: did it start with a release? Check the prompt and model changes in that release.
2. Check the provider status page and whether `LLM_MODEL` changed.
3. Look at a failing trace: `copilot.llm.generate` shows `attempts` and `parse_ok`.
4. Re-run `make eval` against the suspect model or prompt before rolling forward. Roll back with `make rollback` if needed.

### Abstain rate high
More than half of requests abstain for 15 minutes.
1. *Abstentions by source* panel: `gate` means corpus, index or scope problem; `llm` means the model abstains; `low_confidence` or `no_valid_citations` means grounding degraded.
2. `gate`: is `data/processed/chunks.jsonl` present in the image? Did a source update change chunk ids? Compare `copilot.retrieval.top_bm25` across versions.
3. `llm`: compare with the previous version, and re-run the abstention cases in the eval.

### Latency high
p95 above 20 seconds. Retrieval is in memory (milliseconds), so check the LLM latency panel first: almost always the provider. Consider a smaller model, a lower `max_context_chars`, or a timeout and retry policy review.

### Guardrail interventions high
Guardrails are correcting more than 30% of calls. Users stay protected, but the raw model is drifting toward non-read-only commands or invalid citations. Re-run `make eval` (the `raw_model_needed_guardrail_rate` metric) with the current model and prompt.
