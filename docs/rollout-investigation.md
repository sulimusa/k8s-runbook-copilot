# Atlas rollout/OOM capstone demonstration

Question: **does operational knowledge plus adaptive evidence collection improve
investigations?** The demo implements a testable workflow; it has not yet established
an LLM performance improvement.

## Scope and knowledge

This is the Kubernetes Buildcamp capstone, not the financial consulting project.
The fictional Atlas API provides a concrete incident without needing private company
documents. Its service contracts describe normal operation, not an answer to a test case.

The current source manifest builds **131 documents / 696 chunks**:

| Source | Documents | Chunks |
|---|---:|---:|
| Pinned Kubernetes documentation | 44 | 567 |
| Pinned community runbooks | 58 | 91 |
| Existing project lab runbooks | 9 | 18 |
| Reviewed historical incident synopses | 12 | 12 |
| Fictional service operations knowledge | 8 | 8 |

The operations knowledge includes routing, memory, release, telemetry, dependency,
ownership and worker guidance, plus explicitly superseded blue-green guidance.
The full corpus is searched: no case-specific document shortlist is supplied.
Lexical retrieval is BM25; configured embeddings are optional, not needed for RAG.
The routing query also retrieves the archived policy and worker document. Their
status and workload applicability must be considered, not merely their similarity.

The 12 incident documents are project-authored synopses of the already reviewed
patterns, with primary links. They are historical analogies, not verified reproductions
or copied full articles. Tests check that they still match the reviewed pattern records.
The remaining researched incident links are not silently treated as validated knowledge.

Neither `demo/rollout_oom` nor `eval/` is an ingestion source. Answer keys, blind diagnoses
and the 36-case evaluation fixtures are excluded. That broader suite remains unchanged.

## Start the interactive demo

From the repository root, after installing `.[api,dev]`:

```bash
python -m runbook_copilot.ingest.run
uvicorn app.api:app --host 127.0.0.1 --port 8010
```

Open **http://127.0.0.1:8010/demo/rollout-oom** and choose a scenario and mode.
Initial ingestion requires internet to fetch pinned public sources. After the corpus
is built, the browser demo runs offline without credentials, model calls or cluster access.
The Docker runtime includes the replay fixtures as well as the built corpus.

Each report displays the decision and rationale at every step, the returned observations,
retrieved passages, source links/IDs, exact quotes and remaining checks. All content is
escaped before HTML rendering. Reports identify the planner and evidence mode explicitly.

| Scenario | Observation path | Expected distinction |
|---|---|---|
| `routing` | Rollout → routing → memory/traffic | Release selector excludes old ready replicas; overload supported by matching observations |
| `buffer` | Rollout → routing → effective configuration → memory/traffic | Normal routing; buffer setting and matched-work allocations support a configuration regression, not proof of a leak |
| `incomplete` | Rollout → attempted routing → attempted memory capture | Missing data remains unknown; no specific cause established |

RAG inserts document searches between checks, including a second query for the operating
envelope. The synthetic measurement windows are aligned. These fixtures are normalized
observations, not real cluster captures. No workload failure is injected by this demo.

## Planner and tools

`src/runbook_copilot/investigation.py` contains a bounded decision loop with six choices:

- `inspect_rollout`
- `inspect_routes`
- `inspect_configuration`
- `inspect_memory`
- `search_knowledge`
- `finish`

Only requested observations enter the next planner context. The planner never receives
the fixture name, unrequested observations, or expected diagnosis. Repeated observation
reads are refused, duplicate queries are refused, retrieval is capped at three queries
and four passages per query, and the loop has at most 12 steps. No command execution tool
exists. Quote/ID checks (allowing whitespace-only formatting differences) reject forged citations but cannot prove semantic correctness.
Budget exhaustion is recorded separately from a completed insufficient-evidence conclusion.

Two planners can use this same interface:

1. **Offline rule-based demonstration:** the default, visibly labeled. It selects checks
   based on returned facts, not scenario identity. It demonstrates mechanics and guarantees
   reviewers can run the workflow. It is not an LLM and must never be scored as one.
2. **Configured model:** an LLM chooses each tool/query and the final answer through the
   structured Step contract. This uses a bounded provider client and requires explicit
   model configuration. Conversation history preserves the model’s own prior decisions. Unknown tools, writes and unavailable actions are rejected.

To export a new offline report (also creates an adjacent self-contained HTML file):

```bash
python -m runbook_copilot.investigation --case routing --mode rag \
  --output eval/reports/atlas-routing.json
```

Add `--llm` only when intentionally using the configured provider and accepting its usage.
Browser GET endpoints never invoke a model. The explicit POST button and batch runner
use the configured provider and persisted campaign budget. The existing remediation agent is separate and is not invoked by this demo.

## Three-arm experiment

| Mode | Initial alert | Inspection tools | Knowledge retrieval |
|---|---|---|---|
| `baseline` | Yes | No | No |
| `tools` | Yes | Yes | No |
| `rag` | Yes | Yes | Yes |

Use the same pinned model, generation parameters, initial alert and comparable resource
budgets. Compare both status/diagnosis and the usefulness of the chosen checks. Record
missing telemetry handling, irrelevant/superseded document use, citation support, tool
counts, latency, tokens and refusals. The baseline's evidence access intentionally differs;
report this design rather than interpreting all gains as retrieval gains. The tools-versus-RAG
comparison isolates the incremental knowledge access more closely.

The deterministic demo can reach the same diagnosis in tools-only and RAG modes. That is
expected: its rules were authored for the exercise, so it cannot establish an LLM's benefit
from retrieval. Do not publish its outcomes as model accuracy or as proof RAG is necessary.

Actual model responses require a separate blinded review with evidence-based rationale.
Judge source applicability as well as diagnosis; a correct answer with an unsafe or
inapplicable recommendation is not a successful investigation. The 36-case comparison
harness is available for the broader static evidence study; it is not automatically an
evaluator for these multi-step traces. A live adapter, captured failure reproductions and
held-out service scenarios remain future validation work.

## Validation completed locally

- Real corpus ingestion and targeted retrieval, including applicability distractors.
- Original 40-case retrieval gate: hit@5 **1.0** across its 35 retrieval-target cases,
  hit@1 **0.914**, MRR **0.935**. This is retrieval relevance, not diagnosis accuracy.
- Replay protocol tests for all variants and access modes.
- Scripted-model tests for incremental observation access and re-querying.
- Rejection tests for unknown/write actions, forged evidence, repeated reads and budget limits.
- Web route and HTML escaping checks.

Human review of the new synthetic scenarios and controlled baseline/tools/RAG comparisons
are still pending. Real-model development runs and separate judge reviews are described below.


## Run the real model locally

Install `.[api,dev,otel]` and build the corpus first. Copy `.env.example` to `.env`
and enter your own key there; never commit it. The Atlas client uses OpenAI, strict
structured output and a pinned model. It selects typed actions; it does not execute shell
commands or have access to an answer key. Generic triage provider settings are separate.

Set `ATLAS_MODEL` and `ATLAS_JUDGE_MODEL` to the same supported model, and set
`ATLAS_INPUT_PRICE` / `ATLAS_OUTPUT_PRICE` to its verified USD prices per million tokens.
The current shared price fields require both models to have the same prices. For the recorded
`gpt-4.1-2025-04-14` runs these were 2.00 input and 8.00 output; verify
[the model documentation](https://developers.openai.com/api/docs/models/gpt-4.1)
before repeating (this older snapshot is now marked deprecated by the provider). Set `ATLAS_BUDGET_USD=1` for a one-dollar campaign, and
`ATLAS_MODEL_RUNS_ENABLED=true` only if you want the browser’s paid-run buttons enabled.

```bash
# Terminal 1: optional local telemetry, isolated from other projects
make atlas-monitoring
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:14318
export OTEL_METRIC_EXPORT_INTERVAL=2000
uvicorn app.api:app --host 127.0.0.1 --port 8010

# Terminal 2: export the same OTEL variables to trace the batch runs
make atlas-run RUN_DIR=eval/reports/my-new-run
# Review the saved reports, then independently judge them:
make atlas-judge RUN_DIR=eval/reports/my-new-run
```

Use a NEW run directory for each experiment; earlier failures are preserved. Judge preflight
rejects changed fixture/report hashes and existing results before any paid calls. The judge
gets the observations, retrieved material, decisions, candidate answer and evaluator-only
criteria in a fresh context. It does not get the investigator’s model identity or costs.
It rates correctness, grounding, applicability, uncertainty, tool usefulness and safety.
A deterministic gate also checks completion, decisive observations and actual knowledge use.
The judge is a reviewer, not ground truth: same-provider bias and human review remain concerns.

The SQLite campaign ledger in `logs/atlas-budget.sqlite` is shared by all Atlas runs and judges.
Calls reserve conservative estimated cost before sending; unknown outcomes retain reservations.
SDK network retries are disabled. One structured-output repair per step, one reminder for skipped retrieval and one final citation
repair per investigation are allowed, still within the step/input/output/cost bounds. Failed
attempts count in token usage and cost. Never delete the ledger to bypass the campaign limit.
This is a local cost guard using configured prices, not an OpenAI account-level spending limit.

## Monitoring and review

- Demo: http://127.0.0.1:8010/demo/rollout-oom
- Persistent run history and reports: http://127.0.0.1:8010/atlas/monitoring
- Machine-readable run history: http://127.0.0.1:8010/atlas/stats
- Atlas Grafana dashboard: http://127.0.0.1:13000/d/atlas-investigations/atlas-investigations
- Local Prometheus: http://127.0.0.1:19090

Grafana’s lab login is `admin` / `admin`; all published ports bind to loopback. These are
local demonstration settings, not an internet-facing deployment. Compose provisions dashboards
and persists telemetry in its own volume. In Grafana Explore choose **Tempo** to find the
`trace_id` saved with a run, or **Prometheus** for metrics. Spans cover model calls, retrieval,
inspection and separate judge calls. Metrics cover outcomes, latency, calls, tokens and known
cost. No prompt text, observations, keys or answer keys are exported as span/metric attributes.

Counters are process-lifetime signals and reset when the application/batch process restarts;
use the saved JSON reports and campaign ledger for totals across experiments. The persistent
history shows the latest 200 runs, distinguishes offline/model runs and displays unknown cost
explicitly. The Grafana latency quantile is an approximate histogram, not a benchmark based
on three requests. Judge artifacts remain in the run directory; the local dashboard also lists combined evaluation outcomes. Costs are estimates from provider-reported token counts and configured prices, not invoices; cached-input discounts are conservatively ignored. Feedback collection, held-out
cases and a controlled three-arm comparison are still future work.


## Recorded live results — 2026-11-04

Final development batch: `atlas-live-20261104-i`. The three investigations ran locally
against the real OpenAI API, followed by separate fresh-context judge calls. Both investigator
and judge used `gpt-4.1-2025-04-14`, temperature 0. The synthetic fixtures and evaluator keys
were not changed to make the results pass.

| Case | Final outcome | Model calls | Read/search calls | Independent judge + deterministic gate |
|---|---|---:|---:|---|
| routing | supported | 7 | 5 | Pass |
| buffer | supported | 6 | 5 | Pass |
| incomplete | insufficient_evidence | 6 | 5 | Pass |

The full [synthetic results and experiment history](atlas-live-results.json) include model
settings, hashes, diagnostics, citations, scores, costs and all earlier batch outcomes.
Raw reports and failed attempts remain locally in `eval/reports/` and `logs/atlas-runs/`.
The final routing run needed one retrieval reminder, which is visible in its trace; this
is not an unassisted first-attempt success. No failure was silently discarded.

Development exposed repeated actions, missing conversation history, invalid conclusion fields,
and joined/paraphrased quotations. Improvements added decision history, bounded schema repair,
whitespace-only quote normalization, exact-citation feedback and a required retrieval attempt
in RAG mode. Provider/model changes are recorded; these experiments do not isolate which
individual change improved performance.

The judge initially gave full ratings to a buffer answer that skipped routing, and to a
routing answer that skipped retrieval. The deterministic gate rejected both. This is concrete
evidence that the judge alone is not a sufficient quality gate. After revision, all final
cases passed both layers. A separate deliberately false/unsafe answer scored 0 in all six
judge dimensions and was rejected. Reproduce that check against a saved batch with:

```bash
python -m eval.atlas_eval negative-control --directory eval/reports/my-new-run
```

Validation: **213 local tests passed**, Ruff and Bandit passed. An additional real API request
returned the correct insufficient-evidence result, rendered an HTML report and appeared in
persistent history. All three final investigation and judge traces were available in Tempo;
Grafana provisioning and telemetry persistence were checked across a container restart.

Total estimated campaign cost, including development failures, judge calls, the negative
control and API smoke test: **$0.706885 of the $1 cap**. Human review remains pending.
This establishes a working three-case RAG investigation and review workflow; it does not
establish held-out accuracy, superiority over tools-only diagnosis, or production readiness.
