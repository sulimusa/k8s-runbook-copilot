# Roadmap: from capstone to consulting offering

## Phase 0: finish the capstone (now)
- Run `make eval` with your model; record the numbers in `docs/evaluation.md` and the README.
- Run the lab captures, review `evidence.md` files for anything sensitive, commit them, re-run the eval.
- Record a 3-minute demo (script in `docs/resume-and-portfolio.md`) and publish a short write-up.
- Create a **held-out** eval split (10-15 new cases written after the system is frozen).

## Phase 1: harden (2-4 weeks)
- Embeddings + reranker behind the same `Retriever.search()`; keep the ablation table honest.
- LLM-as-judge for groundedness and diagnosis, validated against 30 human-labelled answers.
- Corpus expansion: storage (PV/CSI), HPA, ingress, node/kubelet runbooks, more kubernetes-mixin alerts.
- Alert-first input: accept a Prometheus alert payload (labels/annotations) as the question.
- Docker image, Helm chart, GitHub Actions release, a hosted read-only demo with rate limiting.

## Phase 2: productise for a client (the consulting offering)
Offer: **"Private runbook copilot for your platform team"**, the same architecture pointed at the client's own
runbooks and postmortems, deployed inside their environment.

| Component | Capstone | Client version |
|---|---|---|
| Corpus | public docs + labs | client runbooks, postmortems, alert definitions (their data stays in their VPC) |
| LLM | any OpenAI-compatible | their approved provider or a self-hosted model |
| Input | typed question | Slack/Teams bot, alert-manager webhook, PagerDuty/Opsgenie context |
| Safety | allowlist, citations | + RBAC-scoped read-only service account, audit log, redaction of secrets/PII |
| Eval | 40 public cases | client-specific eval built from their past incidents (the real differentiator) |
| Ops | JSONL log | OpenTelemetry traces, dashboards, drift alerts when docs change |

### Packaging
1. **Discovery sprint (1 week, fixed fee):** inventory runbooks, pick top 10 recurring incident types, build a baseline eval from past incidents, report current retrieval quality.
2. **Pilot (3-4 weeks):** deploy against one team's corpus, Slack integration, weekly eval reports.
3. **Operate (retainer):** corpus freshness, eval regression gates in CI, model upgrades, quarterly review.

### Proof points to build before selling
- Public case study from this repo with real numbers and the honest caveats (credibility).
- A "bring your own runbooks" demo: ingest 20 markdown files in a minute.
- A one-page security note derived from `docs/safety-model.md`.

## Rules to keep the business clean
- Never mix client data into this public repo or its eval sets. Client work lives in private repos.
- Keep the public capstone as the reference implementation; improvements that are generic go back to it.
- Do not claim accuracy numbers from the dev set; quote held-out or client-specific results only.

## Milestone status (market-driven order, see docs/market-analysis.md)
| Milestone | Scope | Status |
|---|---|---|
| M1 Platform | Dockerfile, Helm, build-once/promote CI/CD, OpenTelemetry + Grafana dashboard + alerts, security scans, market analysis | **Built.** Chart render-verified and scanned, telemetry unit-tested; image build, kind deploy, workflows and Grafana stack still to be run by you (`docs/deployment.md`) |
| M2 Retrieval + eval | pgvector hybrid backend (Elasticsearch only as optional ablation, 1.2% of US postings), held-out eval split, validated LLM judge, ablation table | Planned |
| M3 Agents | Dev-acting / prod-advising agent with typed actions, policy, RBAC, rollback, audit, fix-and-verify eval | **Built** and tested on a simulated cluster; run `make agent-eval` on kind to measure it. Still planned: MCP server, Alertmanager webhook, Chaos Mesh scenarios, prompt-injection red-team in CI |
| M4 Optional | Bedrock provider and Terraform AWS deploy with teardown, LiteLLM gateway, Ollama self-hosting comparison, TypeScript UI | Planned |
