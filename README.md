# ☸️ Kubernetes Runbook Copilot

[Capstone submission guide](docs/submission.md) · [Course criteria](docs/course-alignment.md) · [Five-minute walkthrough](docs/demo-script.md)

## Main workflow: investigate cluster history

Ask **“What changed before this failure, and what evidence supports the next step?”**
The assistant reads retained Kubernetes changes, compares current collected state, and retrieves
operational knowledge when needed. It returns a cited timeline, observations versus hypotheses,
missing evidence and a reviewed next step. This is the AI Buildcamp capstone, not a general
cluster-management platform.

Open [historical investigation chat](http://127.0.0.1:8501). Choose **Live cluster history** for the
isolated `runbook-capstone` collector, or **Three capstone demos** for reproducible synthetic
snapshots. The demo uses the same investigation agent and read-tool interface as live chat.
It never contacts Kubernetes and exposes no repair controls.

| Demo | Question | What we test |
|---|---|---|
| Rollout and OOM | Why did cache-api restart after the rollout? | Version-specific cache semantics may improve next checks; budgets do not prove actual allocation. |
| Selector change | Why did demo-web lose endpoints? | Before/after selector and current Pod labels can establish mismatch without RAG. |
| Earlier outage | What caused the outage before collection began? | Neither retrieval nor a model can recover absent history; request evidence. |

Each demo can run **history only** or **history + RAG**. Recorded answers can be inspected without
an API key. New model runs use the existing shared budget; they are explicitly triggered.
The current recorded comparison includes developer-reviewed judge disputes and explicit failure/retry provenance. See the [three-case walkthrough and results](docs/history-demo.md),
[collector setup and limits](docs/cluster-history.md), and
[course alignment](docs/course-alignment.md).

Production chat is read-only. Live dev repair remains a separate explicit button for one bounded
Service-selector restoration, with checks and verification. Endpoint readiness is not proof of
HTTP success or customer recovery. Collection times are observation times, not audit timestamps.

The [earlier rollout/OOM demo](docs/rollout-investigation.md), generic triage API and 36-case suite
remain supporting regression material. They are not the main user journey. The historical
[24-case comparison](docs/knowledge-value-results.md) is separate from the new demonstration.

## Start the capstone UI

From the repository root, after creating a virtual environment:

```sh
uv sync --locked --all-extras
make capstone-demo
```

The app defaults to **Three capstone demos** to show recorded answers with no cluster, corpus download or API
key. To run a new model investigation, configure `.env` as described in `.env.example`, including
an explicit shared API budget and verified token prices. Live history additionally requires the
[dedicated collector](docs/cluster-history.md#reproduce-locally). Nothing connects to another
project's cluster as a fallback.

## Supporting triage and regression interfaces

The sections below document the original public-runbook triage API and separate CLI agent.
Their output schemas and evaluation results do not describe the historical chat's performance.

## Why this exists
Most RAG demos stop at "retrieve and summarise". Incident triage needs the opposite instincts: **say "I don't know"**,
**cite everything**, and **never suggest something destructive**. This project makes those behaviours testable:

| Behaviour | How it is enforced | How it is measured |
|---|---|---|
| Grounded in sources | numbered context + citation subset check + lexical groundedness | groundedness, citation hit rate |
| Abstains on weak evidence | retrieval gate (no LLM call) + model abstention + confidence cap | abstention correctness |
| Read-only | command allowlist, remediation sanitiser | command safety, guardrail-intervention rate |
| Reliable output | Pydantic schema + validate-and-retry | parse success rate |
| Observable | OpenTelemetry traces + metrics, JSONL logs with trace ids, Grafana dashboard, alert rules | latency p50/p95, parse failures, retrieval scores, tokens, cost |

## Output contract
```python
class TriageResponse(BaseModel):
    found_answer: bool
    incident_type: str            # CrashLoopBackOff | ImagePullBackOff | OOMKilled | PodPending | ProbeFailure |
                                  # DNSServiceConnectivity | FailedRollout | ResourceQuotaOrNodePressure | Unknown
    summary: str
    likely_causes: list[str]
    evidence: list[str]           # short quotes/paraphrases from cited chunks
    diagnostic_commands: list[str]    # read-only kubectl only (allowlisted)
    remediation_guidance: list[str]   # advice for a human; write actions are flagged "[Manual change ...]"
    confidence: float             # 0-1, capped by groundedness
    citations: list[str]          # chunk ids, e.g. k8s-runbooks:kubernetes/KubePodCrashLooping#00
    answer_not_found_reason: str | None
```
Illustrative shape of a response (not a recorded model output):
```json
{
  "found_answer": true,
  "incident_type": "CrashLoopBackOff",
  "summary": "The container is repeatedly exiting and being restarted. Check events and previous logs to find the exit reason.",
  "likely_causes": ["Application error at startup", "Probe misconfiguration"],
  "evidence": ["Check pod events via kubectl describe pod", "readiness and liveness probes may be incorrect"],
  "diagnostic_commands": ["kubectl -n <namespace> describe pod <pod-name>", "kubectl -n <namespace> logs <pod-name> --previous"],
  "remediation_guidance": ["Consider correcting probe port/timeouts after verifying in a non-production environment."],
  "confidence": 0.82,
  "citations": ["k8s-runbooks:kubernetes/KubePodCrashLooping#00"],
  "answer_not_found_reason": null
}
```

## Architecture
```
public sources (pinned git SHAs) ─► parse ─► heading-aware chunks ─► chunks.jsonl (+ optional embeddings)
                                                                           │
question ─► BM25 (+dense, RRF) ─► retrieval gate ──weak──► abstain (no LLM call)
                                      │ ok
                                      ▼
              prompt + numbered context ─► LLM (any OpenAI-compatible) ─► Pydantic validate (retry once)
                                      ─► guardrails: citations ⊆ retrieved · command allowlist ·
                                         remediation flags · groundedness ─► TriageResponse + trace
```
Details and design decisions: [docs/architecture.md](docs/architecture.md).

## Quickstart
```bash
git clone https://github.com/sulimusa/k8s-runbook-copilot.git && cd k8s-runbook-copilot
python -m venv .venv && source .venv/bin/activate
make install                    # pip install -e ".[app,otel,dev]"
make ingest                     # fetch public sources at pinned commits, parse, chunk (~1 min)
make search Q="pod stuck in CrashLoopBackOff"     # retrieval only, no API key needed
make eval-retrieval             # no API key needed
make test

cp .env.example .env            # add LLM_API_KEY (any OpenAI-compatible endpoint; Ollama works too)
make eval                       # full-pipeline evaluation
streamlit run app/runbook_ui.py  # Original public-runbook demo  (or: make serve  -> http://localhost:8000/docs)
```
Without an API key, `/search` works in retrieval-only mode. The history UI can display saved demo answers; generating new answers requires a configured model.

### API
```bash
curl -s localhost:8000/triage -H 'content-type: application/json' \
  -d '{"question":"Pod is Pending with FailedScheduling: Insufficient cpu"}' | jq
```
`GET /health`, `GET /stats` (request-log summary), `GET /sources`, `POST /search` (retrieval only). Traces and metrics go to OTLP when `OTEL_ENABLED=true`.

## Agent mode: fixes in dev, advice in prod
```bash
make agent-access ENV=dev NS=lab-oomkilled     # scoped identity + opt-in label (local kind cluster)
make agent ENV=dev NS=lab-oomkilled INCIDENT="my service keeps restarting"     # diagnose, fix, verify, roll back if needed
make agent ENV=prod NS=prod INCIDENT="..."     # read-only identity: prints a proposal, changes nothing
```
The model proposes one of 8 typed actions (never a command). Every write needs a retrieved doc citation, a verbatim evidence
quote and a policy allow; every change is dry-run, verified against the target workload, and rolled back if it did not help.
Unfixable problems are escalated, not guessed. Tested on a simulated cluster; **not yet run on a real one** (see the guide).

## Run it like a platform
```bash
docker compose up --build        # Copilot + Grafana (traces, metrics) on :3000
LLM_API_KEY=sk-... make platform-up   # kind cluster, build once, deploy to dev, observability backend
make promote                     # prod gets exactly the image that runs in dev (no rebuild)
make rollback                    # prod back one Helm revision
make audit                       # bandit + pip-audit
```
Helm chart: non-root, read-only filesystem, no service-account token, NetworkPolicy, PDB in prod.
CI: tests, lint, security scans, retrieval eval gate, Helm lint, build-once image with SBOM, promote-by-digest.
See [docs/deployment.md](docs/deployment.md) and [docs/observability.md](docs/observability.md) (including what was and was not run).

## Data
Official Kubernetes docs (CC BY 4.0), Prometheus Operator / kubernetes-mixin runbooks (Apache-2.0), plus original
lab runbooks and lab evidence. All remote content is fetched at **pinned commits** and not committed.
See [data/SOURCES.md](data/SOURCES.md) and [NOTICE.md](NOTICE.md).

## Lab scenarios
Eight disposable failure scenarios for kind/k3d/minikube (`labs/`), one per incident category, with a capture script that
records read-only `kubectl` output as additional evidence. `make lab SCENARIO=crashloop`. See [labs/README.md](labs/README.md).

## Evaluation
The [service-knowledge value study](docs/knowledge-value-evaluation.md) compares question-only,
evidence-only and evidence-plus-RAG investigations on **24 fictional cases**. It includes
version-dependent decisions, cases where retrieval should add nothing, and missing-contract
cases. A frozen development retrieval audit found wrong-scope contracts in 11/12 unfiltered
searches; scope filtering removed them while preserving 6/6 decisive contracts. This is
**document-selection evidence**. The [live comparison](docs/knowledge-value-results.md) is now complete:
72 model answers, with higher judge-rated usefulness in 11/12 service-specific cases and ties
on generic/missing-contract cases. Judge defects and answer overconfidence are documented;
factual accuracy superiority is not established. Answer keys remain outside retrieval.

The [Atlas rollout/OOM investigation demo](docs/rollout-investigation.md) searches the broad
131-document corpus and exposes a read-only, multi-step investigation with three contrasting
synthetic scenarios. Open `/demo/rollout-oom` on the API server. The browser version uses an
explicitly labeled offline rule-based planner, plus an opt-in real-model button and batch runner. The final three-case model batch passed the judge and deterministic checks; earlier failures are retained.
It does not inject cluster failures, execute remediation or claim measured LLM improvement.

An additional [evidence-first incident study](docs/incident-study.md) provides 36 synthetic
scenarios across 12 report-inspired families, including counterfactuals and missing-evidence
variants. Its offline harness exports baseline and pattern-assisted prompts with separate
answer keys. The comparison workflow freezes both arms, checks response provenance, prepares
randomized A/B judge packets and reports ratings by family and scenario type. This is a
candidate study, not a measured model-quality result or live reproduction.

40 cases across 8 incident categories plus abstention and safety cases. Measured retrieval results on the pinned corpus:

| Setup | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| Public sources + lab runbooks | 0.914 | 0.971 | 1.000 | 0.939 |
| Public sources only (ablation) | 0.771 | 0.943 | 1.000 | 0.864 |

Full-pipeline metrics (abstention, diagnosis accuracy, safety, groundedness, latency, parse rate) come from `make eval`.
**Caveat:** this is a dev set; gate thresholds were tuned on it. See [docs/evaluation.md](docs/evaluation.md) for metrics, caveats and how to extend.

## Project layout
```
src/runbook_copilot/   ingest/ retrieval/ llm/ safety.py pipeline.py observability.py schemas.py config.py
app/                   api.py (FastAPI) · ui.py (Streamlit)
eval/                  cases/*.yaml · metrics.py · run_eval.py · reports/
labs/                  kind config · 8 scenarios · capture.sh
data/                  sources.yaml · lab_runbooks/ · lab_evidence/ · (raw, processed, index are generated)
deploy/                Helm chart · kind scripts · agent RBAC + access script · lab observability manifest
observability/         dashboard generator + JSON · alert rules
analysis/job_market/   reproducible market analysis (script only; no raw data)
docs/                  architecture · safety-model · evaluation · observability · deployment · design-decisions ·
                       market-analysis · skills-evidence-map · roadmap · resume-and-portfolio
tests/                 156 tests (parsing, chunking, safety, retrieval, pipeline, telemetry, API, eval harness, agent policy/actions/RBAC/loop on a simulated cluster)
policies/              dev.yaml (act) · prod.yaml (advise)
```

## Limitations
- Focused corpus (pods, probes, scheduling, services/DNS, quotas, rollouts); out-of-corpus topics should abstain.
- Groundedness is lexical (a proxy). It cannot catch a fluent but wrong paraphrase.
- Node-pressure scenarios are not reproduced in the lab (unsafe on a laptop); that category relies on public docs.
- A triage suggestion is a starting point for a human, not a diagnosis. Run recommended commands under a read-only role.

## License
Code: Apache-2.0. Third-party content retains its own license; see [NOTICE.md](NOTICE.md).
