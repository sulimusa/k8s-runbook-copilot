# Skills evidence map

What this lab demonstrates, mapped to how often US AI-engineering postings mention each skill
([docs/market-analysis.md](market-analysis.md): 3,160 unique US postings, Feb to Sep 2026) and to where the evidence lives.
Status is honest: **Done** means built and tested here; **Written, not run** means the artifact exists but was not executed
in the environment where it was authored; **Planned** is a later milestone.

| Skill (US share of postings) | Evidence in this repo | Status |
|---|---|---|
| RAG 37.8%, prompt engineering 33.0% | ingestion, heading-aware chunking, BM25 + optional hybrid, gate, prompt contract (`src/runbook_copilot`) | Done (embeddings path implemented, not yet exercised) |
| LLM evaluation 27.6% | 40-case suite, retrieval and full-pipeline metrics, ablation, CI gate (`eval/`, `docs/evaluation.md`) | Done; held-out set and validated judge in M2 |
| Guardrails 15.8%, Responsible AI 7.9% | command allowlist, citation check, groundedness, abstention, remediation flags, safety model (`docs/safety-model.md`) | Done; red-team tests in M3 |
| LLM integration: tokens, latency, cost, reliability | token and cost tracking, validate-and-retry, structured output (Pydantic) | Done; multi-provider gateway planned (M4) |
| Observability 24.9%, monitoring 13.7% | OpenTelemetry traces and metrics, Grafana dashboard, alert rules, runbooks (`docs/observability.md`) | Instrumentation Done and tested; stack Written, not run |
| CI/CD 29.5% | verify, build-once, promote-by-digest workflows | Written, not run |
| Docker 18.0%, Kubernetes 19.8% | multi-stage non-root Dockerfile, Helm chart (hardened pod, NetworkPolicy, PDB), kind lab scripts, Chaos Mesh scenarios | Chart render-verified and scanned; image build and kind deploy not run |
| Security / DevSecOps | bandit, pip-audit, Trivy config scan, input-validated git fetch, read-only filesystem, no service-account token | Done (image vulnerability scan runs in CI) |
| Python 66.8%, FastAPI 6.5%, APIs 27.1% | FastAPI service with typed models, health checks, `/search` retrieval-only mode | Done |
| Vector databases 22.2%, PostgreSQL 11.7%, pgvector 3.0% | pgvector hybrid backend with ablation vs BM25 | Planned (M2) |
| AI agents 43.6%, agentic workflows 33.9%, function calling 16.9% | environment-aware agent: typed actions (Pydantic-validated JSON, not a vendor tool-calling API), policy engine, RBAC identities, verify and rollback, audit trail, fix-and-verify eval (`docs/agent-mode.md`) | Built and tested on a **simulated** cluster; not yet run on a real one |
| MCP 14.1%, LangGraph 11.1% | MCP server, LangGraph orchestration | Planned (the loop is a plain, testable state machine; an adapter is optional) |
| AWS 36.8%, Bedrock 6.4%, Terraform 10.2% | Bedrock provider option, ephemeral Terraform deploy with teardown | Planned (M4, optional) |
| TypeScript 23.2%, React 14.9% | small web UI | Planned (M4, optional) |
| Fine-tuning 17.0% | none | Skipped: does not fit this problem |
| LangChain 16.9% | none in the core pipeline | Deliberate: see `docs/design-decisions.md` #8 |

## Resume bullets (facts only; fill the brackets from your own runs)
- Built a read-only, source-cited Kubernetes triage assistant (Python, FastAPI, Pydantic) on public data pinned to git commits; retrieval hit@5 100% / MRR 0.86 on public sources only across 35 answerable eval cases (dev set).
- Enforced safety outside the model: read-only `kubectl` allowlist, citation verification, remediation flagging, abstention; command safety `[X]%` and guardrail-intervention rate `[X]%` over 40 cases.
- Instrumented the service with OpenTelemetry (traces, metrics, token and cost tracking) with per-release dashboards and four actionable alerts.
- Packaged for Kubernetes: non-root, read-only-filesystem Helm chart, build-once/promote-by-digest CI/CD, Trivy/bandit/pip-audit gates; 69 automated tests.
- Reproduced a market analysis of 7,375 unique postings (open dataset) to choose which skills to demonstrate: `[add the one decision it changed]`.

## Interview notes
Be ready to explain each "Written, not run" item as work in progress, and to show what you ran yourself. An honest "I built it,
here is what I verified and here is what broke when I first ran it" is stronger than a polished claim you cannot demo.
