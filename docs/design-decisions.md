# Design decisions (ADR-style, for interviews)

Each entry: context, decision, trade-off, what would change my mind.

**1. BM25 first, embeddings optional.** Troubleshooting text is dominated by exact tokens (reason codes, event strings, alert names). BM25 hit@5 is 100% on the 35 answerable dev cases with public sources only (MRR 0.864). Trade-off: weaker on paraphrased symptoms. Revisit when held-out eval shows paraphrase misses; pgvector hybrid is the planned upgrade, evaluated as an ablation, not assumed.

**2. Own BM25 instead of minsearch.** The abstention gate needs a score; minsearch's TF-IDF search does not expose one. About 40 lines of pure Python. Revisit if the corpus outgrows in-memory search.

**3. Guardrails outside the model.** A prompt asking for read-only commands is a request, not a control. The allowlist, citation-subset check and remediation sanitiser run after generation and are unit-tested. `raw_model_needed_guardrail_rate` measures how often the prompt alone would have failed.

**4. Abstain before spending tokens.** A retrieval gate (scope, score, coverage) skips the LLM on weak evidence. Trade-off: heuristic thresholds tuned on a dev set with thin margins. A held-out set is the fix. The gate is a cost optimisation; the model and confidence cap are the real abstention paths.

**5. Read-only by construction (triage), identity-bounded (agent).** The triage service has no Kubernetes client, no credentials, and no service-account token in the cluster. It can only return text. Agent mode is a separate CLI whose power comes from the kube identity the operator gives it: dev can make four narrow kinds of change per labelled namespace, prod has no write verbs at all.

**6. OpenTelemetry for instrumentation.** Vendor-neutral. The dashboard and alerts are backend-agnostic PromQL; the lab uses Grafana's all-in-one image to keep laptop RAM manageable. Question text never enters telemetry.

**7. Build once, promote by digest.** Rebuilding for prod can change dependencies or corpus content. The promoted artifact is the tested digest.

**8. Custom pipeline instead of LangChain.** Job postings name frameworks interchangeably, and the pipeline is small enough that a framework would hide the parts worth understanding (gate, guardrails, validation retry). LangGraph is reserved for the agent mode where orchestration earns its place.

**9. Cost from user-supplied prices.** Token counts come from the provider response. Prices are env variables copied from the pricing page, because hard-coded prices go stale silently.

**10. Typed actions, not generated commands.** An allowlist of command strings is a filter on text the model controls. Typed actions invert it: the model fills validated fields in one of 8 shapes and our code builds the argv. Trade-off: the agent can only do what I modelled; that is the point. Revisit by adding one action at a time with bounds, tests and an RBAC verb.

**11. Enforce at the identity first.** Policy can have bugs. RBAC is enforced by the API server, so it still holds. The prod kubeconfig has no write verbs, so even a total failure of the policy layer cannot change prod. Both layers are tested, and a test keeps the RBAC manifests aligned with what the code needs.

**12. Verify against the target, judge independently.** After a write, success means the target workload is healthy and nothing new broke (not "no problems anywhere", or one unrelated fault would roll back every fix). In evaluation, the admin re-checks the namespace so "resolved" never rests on the agent's own claim.

## What breaks at 10x scale
- In-memory BM25 over a larger corpus: move to Postgres full-text plus pgvector or a search service, behind the existing `search()` shape.
- Per-request LLM latency dominates: add timeouts, a smaller model for easy cases, response caching keyed on normalised question plus corpus version.
- Eval cost: sample production traces for online evaluation instead of running the full suite per change.
- Corpus freshness: pinned SHAs trade freshness for reproducibility; add a scheduled re-ingest PR that must pass the eval gate.
