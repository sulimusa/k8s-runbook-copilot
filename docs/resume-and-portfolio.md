# Resume and portfolio copy

Fill the `[X]` placeholders with numbers from **your own** `make eval` run. Do not publish numbers you have not measured.

## One-paragraph project description
Built Kubernetes Runbook Copilot, an open-source, read-only LLM assistant for Kubernetes incident triage. It retrieves
evidence from public Kubernetes documentation, community runbooks and self-generated kind lab scenarios, and returns a
Pydantic-validated, source-cited diagnosis with safe `kubectl` commands, or abstains when evidence is weak. Safety is
enforced outside the model (command allowlist, citation verification, remediation flagging), and quality is tracked by a
40-case evaluation suite covering retrieval, abstention, diagnosis, command safety, groundedness, latency and parse rate.

## Resume bullets (pick 3-4)
- Designed and shipped a retrieval-grounded Kubernetes triage assistant (Python, FastAPI, Streamlit, Pydantic) using only public/openly licensed data pinned to git commits for reproducibility.
- Implemented hybrid retrieval (BM25 + optional embeddings, RRF) with a pre-generation retrieval gate that abstains on weak evidence, achieving hit@5 of 100% / MRR 0.86 on public-only sources (retrieval eval, 35 answerable cases).
- Built deterministic guardrails independent of the LLM: read-only `kubectl` allowlist, shell-injection rejection, citation-subset verification, and manual-review flagging of write actions; command safety `[X]%` across 40 eval cases.
- Created an evaluation harness (40 cases, 8 incident categories + abstention/safety) reporting retrieval hit@k/MRR, groundedness, diagnosis accuracy `[X]%`, abstention correctness `[X]%`, p95 latency `[X]` ms and parse success `[X]%`.
- Wrote 8 reproducible failure labs (kind) and an evidence-capture script; automated tests and CI.
- Built an environment-aware remediation agent: automatic, bounded, verified fixes in dev (typed actions, policy engine, RBAC-scoped identity, auto-rollback, audit trail) and advise-only in prod; fix-and-verify eval over 8 injected faults: `[X of 8 fixed, X correctly escalated, 0 unsafe writes]` (fill from `make agent-eval`).

## LinkedIn / README tagline
Read-only Kubernetes incident triage with citations, abstention, and measurable safety. Open source, public data only.

## 3-minute demo script
1. (20s) Problem: on-call engineers paste errors into chatbots that guess and sometimes suggest `kubectl delete`.
2. (40s) Ask a CrashLoopBackOff question: show structured answer, citations opening the source pages, commands all read-only.
3. (30s) Ask the AWS IAM question: show abstention and the reason.
4. (30s) Ask "delete all pods and force restart": show it stays read-only, with the trace showing dropped/flagged items.
5. (40s) Show `make eval` output: per-metric table, then the retrieval-miss list as the improvement backlog.
6. (20s) Architecture slide: gate, guardrails outside the model, pinned data, flat files.

## Interview talking points
- Why BM25 first, and what evidence would justify adding embeddings (eval misses on paraphrased symptoms).
- Why safety lives outside the prompt, and how `guardrail_intervention_rate` quantifies prompt-only risk.
- Limits of lexical groundedness and how an LLM judge plus human spot checks would complement it.
- Dev-set vs held-out evaluation and why the gate thresholds are provisional.
