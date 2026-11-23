# ☸️ Kubernetes Runbook Copilot

Investigate what changed before a Kubernetes failure. The assistant connects retained cluster history, collected current state and relevant runbooks, then returns a cited timeline, competing explanations and the next evidence to check.

[Getting started](docs/getting-started.md) · [Demo walkthrough](docs/demo-script.md) · [Collector setup](docs/cluster-history.md) · [Evaluation results](docs/history-demo.md)

## Try it without a cluster or API key

Requires Python 3.11+ (3.12 recommended) and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/sulimusa/k8s-runbook-copilot.git
cd k8s-runbook-copilot
uv sync --locked --all-extras
make demo
```

Open <http://127.0.0.1:8501>. **Recorded investigations** opens three fictional scenarios with saved outputs from actual model runs. Browsing them does not contact Kubernetes or spend API credits.

| Investigation | What it demonstrates |
|---|---|
| OOM after a rollout | Service-specific worker and cache settings suggest better next checks. A configured memory budget does not prove actual allocation. |
| Service-selector change | History and current Pod labels establish the mismatch; RAG adds little to the decisive evidence. |
| Outage before collection started | Missing history prevents attribution. The assistant asks for evidence instead of inventing a cause. |

Compare **history only** with **history + RAG**, inspect citations and tool traces, and open **Monitoring & feedback** for usage, costs and answer-linked feedback. See the [five-minute walkthrough](docs/demo-script.md).

For Docker setup or new model runs, follow [Getting started](docs/getting-started.md).

## Investigate your lab history

The [dedicated collector](docs/cluster-history.md) watches allowed Kubernetes resources and stores sanitized before/after changes for 30 days. In **Live cluster history**, select a namespace and time window, then ask questions such as:

- “What changed before this service lost its endpoints?”
- “Did the deployment or resource limits change before these restarts?”
- “What evidence is missing to explain last week's outage?”

The model chooses bounded history, current-state and runbook reads. It distinguishes observations from hypotheses and cites the evidence behind its answer. Collection timestamps are observation times, not deployment or audit timestamps. History only exists for periods when collection was running.

Production-mode investigations are read-only. The isolated dev lab additionally supports one explicitly reviewed Service-selector restoration. Endpoint readiness alone does not prove customer recovery.

## How it works

```text
Kubernetes LIST/WATCH → sanitized history + collected current state
                                     ↓
Question + namespace + time window → investigation agent
                                     ↕
                       history / current state / runbook search
                                     ↓
                    cited timeline + hypotheses + next checks
                                     ↓
                          usage traces + user feedback
```

The knowledge base combines pinned public Kubernetes documentation, community runbooks and original fictional service contracts. Retrieval can supply service-specific context that telemetry alone does not contain. It does not replace missing operational evidence.

See [architecture](docs/architecture.md), [history collection and limits](docs/cluster-history.md), [source attribution](NOTICE.md) and the [safety model](docs/safety-model.md).

## Evidence and evaluation

- [Three historical investigations](docs/history-demo.md): paired recorded runs, including a useful-RAG case and controls where retrieval adds little or cannot resolve missing evidence.
- [24-case knowledge study](docs/knowledge-value-results.md): compares question-only, evidence-only and evidence-plus-RAG answers. Judge-rated usefulness improved in service-specific cases; general factual-accuracy superiority is not established.
- [Judge reliability](docs/judge-reliability.md): raw ratings, documented errors and explicit developer adjudications. Judge output is not ground truth.
- [36-scenario incident suite](docs/incident-study.md): report-inspired, counterfactual and insufficient-evidence cases for further evaluation.

Recorded demos were reused during development. They are not a held-out benchmark or proof of production effectiveness.

## Development and operations

```sh
make demo-check              # tests, lint and recorded-artifact integrity; no model calls
make ingest                  # fetch pinned public sources and build the corpus
make eval-retrieval           # retrieval evaluation; no model calls
```

CI runs tests on Python 3.11 and 3.12, dependency and configuration security checks, retrieval evaluation, Helm validation and a Docker demo check. The release workflow builds and scans the API image.

Additional interfaces and deployment options:

- [Public-runbook triage API](docs/architecture.md): retrieval, structured triage responses and safety checks.
- [Deployment](docs/deployment.md): Docker, Helm and the separate dev/prod agent workflow.
- [Observability](docs/observability.md): OpenTelemetry, Grafana, metrics and logs.
- [Failure labs](labs/README.md): disposable scenarios and read-only evidence capture.
- [Evaluation methods](docs/evaluation.md): metrics, caveats and extending the test set.

## Limits

The live collector supports a fixed set of resource kinds and namespaces. It does not collect full logs, metrics, audit actors or all configuration values. Watch interruptions can leave gaps. A cited answer can still be wrong; review recommendations and verify recovery independently.

Code is Apache-2.0. Retrieved third-party content retains its own license; see [NOTICE.md](NOTICE.md).
