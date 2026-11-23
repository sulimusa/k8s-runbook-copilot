# AI Buildcamp course alignment

> **Current milestone — November 22:** the main flow is now [historical investigation](history-demo.md), with six paired real-model runs over three synthetic history snapshots, structured reports, checked timeline timestamps and preserved failed attempts. [Judge reliability work](judge-reliability.md) separates reference completeness from factual review and queues disputed ratings. The collector is isolated from other projects. The older audit below is historical; independent human review, new held-out cases and a reviewer-accessible published release remain open.

> **Progress update — 2026-11-04:** the Atlas live-model path, separate answer/trajectory judge,
> negative control and local trace/metric dashboards are now implemented and exercised.
> See [recorded results and limitations](rollout-investigation.md#recorded-live-results--2026-11-04).
> The audit below remains the original snapshot; its live-model/judge/monitoring gaps have
> progressed. Human review, feedback collection and controlled held-out comparison remain open.


Reviewed on 2026-11-04. **Kubernetes Runbook Copilot fits the course, but the current local version is not yet ready for submission as a demonstrated, evaluated AI agent.** Its strongest evidence is the retrieval implementation, structured contracts, safety tests and reproducible synthetic investigations. The remaining priorities are actual model runs, evaluation of answers and tool choices, monitoring of that same workflow, and a reviewer-accessible release.

## Scope and source of requirements

The course reference is [ai-engineering-buildcamp-code at commit 4550c847](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/tree/4550c847f8173a837bae6e88cee007756a8b9b4c), dated 2026-09-26. The review inventoried all 570 repository files and examined the substantive Python, notebook source cells, Markdown and project configuration across every teaching area: 104 nonempty files plus four empty package initializers. Generated PDF extraction pages, binary documents, notebook outputs and large saved runs were not reviewed line by line; representative evaluation artifacts were inspected. [The review inventory](course-review-inventory.json) records paths and Git blob identifiers.

The public repository contains foundation, RAG, agents and multi-agent examples, plus a documentation application with testing, monitoring and evaluation. It does not contain the complete grading rubric supplied in the course portal. Point ceilings below come from the rubric the student supplied; implementation comparisons come from the repository. No grading outcome is guaranteed.

This audit covers the local working tree based on `885e33b0c7ddbad413233f87d5de49f706df089f`. GitHub `main` was still at that initial-import commit when checked. The Atlas investigation and incident-study additions are local uncommitted work; a reviewer cloning GitHub will not receive them yet.

## The real user and problem

The first user is the project owner, a DevOps engineer investigating Kubernetes failures in a lab and preparing to explain those investigations to peers. An OOM alert alone does not distinguish a traffic-routing problem from a configuration change. The engineer must connect current observations with the applicable service contract, reject outdated or wrong-workload guidance, and decide which missing check would resolve uncertainty.

The proposed capstone output is a cited investigation report: supported mechanism or insufficient evidence, observations used, applicable documentation, conflicting evidence and next checks. It must not claim to have repaired a cluster. Atlas is a fictional service for reproducible exercises; its fixtures do not establish effectiveness on production incidents.

The useful role of RAG is retrieving service-specific and version-specific operating knowledge that the model cannot safely infer from generic Kubernetes knowledge. The useful role of the agent is choosing the next inspection or document query after observing earlier results. Corpus size alone is not the value proposition. Measure whether the retrieved knowledge changes the quality of an investigation.

To establish usefulness, record the project owner completing a few investigations and invite a peer to try unseen variants. Capture whether they reached a supported conclusion, identified a useful next check and avoided unsupported advice. Timing can be descriptive, but repeated exposure to the same scenario creates a learning effect; do not call a small practice session a controlled productivity study.

## Course lessons mapped to this project

| Course area and source | Existing capstone evidence | Remaining work or deliberate scope choice |
|---|---|---|
| [Foundation: retrieval, chunking and grounded generation](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/01-foundation/02-rag/rag.ipynb) | `src/runbook_copilot/ingest/`, `retrieval/`, `pipeline.py`; pinned sources, heading-aware chunks, BM25, cited answers and abstention. | Preserve this foundation and demonstrate it in actual model responses. |
| [Structured output](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/01-foundation/03-structured-output/notebook.ipynb) | Pydantic `TriageResponse`, investigation `Step` and `Citation`, validation and bounded repair attempts in `llm/client.py`. | Record real parsing failures and recovery. Structured output guarantees shape, not a correct diagnosis. |
| [Vector search bonus](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/01-foundation/04-bonus/vector-search.ipynb) | Optional embedding index and reciprocal-rank fusion exist. Current verified corpus retrieval uses BM25; no local embedding index is present. | BM25 is valid RAG. Compare hybrid retrieval only if error analysis exposes a retrieval problem; do not claim it has been evaluated. |
| [RAG use cases and reusable pipelines](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/tree/4550c847f8173a837bae6e88cee007756a8b9b4c/02-rag-usecases-tech) | Reusable retrieval/pipeline modules, source manifests and persistent chunk files. The corpus has 131 documents and 696 chunks. | FAQ, YouTube and mathematics-PDF examples demonstrate alternative inputs. Adding those formats to Kubernetes triage would not improve course alignment by itself. |
| [Agent tool loop](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/03-agents/02-agent-basics/tool-call-loop.ipynb) | `investigation.py` allows four evidence inspections and knowledge search, with state, re-querying, step budgets and termination. Model mode is implemented and tested with scripted providers. | Run a real LLM through these tools. The implementation uses structured JSON dispatch rather than provider-native function-call messages. Explain that design and show the model-selected trace; the default browser replay is rule-based, not an LLM agent. |
| [Documentation agent with search and full-file retrieval](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/doc_agent.py) | Repeated knowledge search and citation provenance checks. | A bounded document-section reader could help when a truncated passage lacks a critical qualifier. Add it only for an observed failure, with allowlisted document IDs and length limits. |
| [Workflows versus model orchestration](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/04-testing/multi-agent/workflows_vs_orchestrated.py) | Offline policy and model planner share a bounded execution interface; the distinction is documented. | Show that the LLM changes its next check when the observed facts change. A swarm, handoffs and every multi-agent pattern are unnecessary. A separate evaluator is useful without making the runtime multi-agent. |
| [Tests with an LLM judge](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/tests/test_judge.py) | Extensive deterministic unit tests, scripted-model protocol tests and a frozen automated review of the 36 scenarios. | Add opt-in semantic judge tests on actual investigator outputs. Reviewing fixture plausibility is different from testing the answering agent. |
| [Manual and synthetic evaluation](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/evals/README.md) | 40 common-symptom cases; 36 report-inspired cases with isolated answer keys; three multi-step Atlas replays; comparison manifest and randomized answer packets. | Run the answering model and evaluator, save failures, manually label a sample, and use measured errors to improve the system. The static 36-case harness is not yet an evaluator for the Atlas trajectories. |
| [Correctness, instruction and trajectory judges](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/evals/synthetic/judge.py) | Five proposed answer dimensions and strict citation/command checks in the study harness. | Extend evaluation to tool usefulness, unnecessary calls, missing decisive checks and applicability of documents. Judge rationale must reference evidence. |
| [Monitoring and feedback](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/app.py) | Original triage pipeline has OpenTelemetry, JSONL logs, token/cost accounting, Grafana dashboard definition and alert rules. Atlas reports record decisions, observations, durations and token totals. | Instrument Atlas model/tool/retrieval spans and demonstrate populated dashboard panels. Add response-linked user feedback. Existing triage telemetry does not automatically cover Atlas. |
| [Turning traces into evaluation material](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/trace_replay/README.md) | Investigation reports already preserve replayable observations and a trace. | Export selected failed runs for human annotation and create regression examples. Preserve provenance and keep evaluator keys outside retrieval. No need to adopt Logfire specifically. |
| [Project tooling](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/4550c847f8173a837bae6e88cee007756a8b9b4c/documentation-agent/pyproject.toml) | Package structure, Makefile, Dockerfile, CI/release workflows, FastAPI and Streamlit. | Verify a clean setup and published workflow run. Dependencies currently have lower bounds, not a lock; adopt `uv` and a lock or another documented reproducible resolution if useful. |

Provider alternatives, streaming, web search, multi-format document extraction and elaborate multi-agent patterns are lesson examples, not a requirement to reproduce every feature. PydanticAI and Logfire are replaceable implementation choices. The course's own basic RAG starts with lexical retrieval, so vector infrastructure is not a prerequisite for the RAG criterion.

## Validation performed for this audit

| Check | Result and limits |
|---|---|
| Unit and integration-style tests | **198 passed, no skips** using the local virtual environment. Initially 193 passed and two skips were reported because `opentelemetry.sdk` was absent; installing the already-declared `.[otel]` extra enabled those tests. Providers and cluster actions in these tests are simulated. |
| Ruff | Passed across source, application, evaluation, tests, analysis and observability code. |
| Bandit | Passed; two existing unused suppression warnings in `eval/agent_eval.py`. This is static analysis, not a dependency-vulnerability or deployed security assessment. |
| Retrieval evaluation | 40 cases, 35 with expected retrieval targets: hit@1 **0.914**, hit@3 **0.943**, hit@5 **1.000**, MRR **0.935**. No answerable case blocked by the gate; the gate catches 3/5 abstention cases. Remaining abstentions require model behavior. |
| Incident fixtures | 36 cases across 12 families pass structural validation; recorded automated review matches current hashes. Human review remains pending. |
| Corpus | 44 Kubernetes docs, 58 community runbooks, 9 lab runbooks, 12 incident synopses and 8 fictional service documents. No captured lab-evidence documents in this build. |
| Actual AI quality | Not established by this audit. No paid model calls were made. The comparison directory contains prompts and schema, not completed response/judge results. |
| Deployment and monitoring | Configuration and tests inspected. A running Grafana dashboard with Atlas usage, a fresh Docker build, clean-clone setup and successful published CI were not established here. |

The retrieval suite is a development set used for threshold tuning. Its expected-source matching is not semantic diagnosis accuracy. The published README/evaluation tables still include an older corpus run with different hit@3/MRR values; retain that only as a dated historical result, or replace it with a clearly identified current run before submission.

## Rubric readiness

The status refers to submission evidence, not only the existence of code.

| Supplied rubric category | Ceiling | Current readiness | Evidence needed to claim full credit |
|---|---:|---|---|
| Problem in README | 2 | Partial | Lead with the named user, concrete investigation problem and success criteria; add a short real-user trial. |
| Knowledge base and RAG | 2 | Strong | Explain provenance/chunking/retrieval and show applicable citations in actual model investigations. |
| Agents and LLM tools | 3 | Partial | Demonstrate the configured LLM selecting multiple tools and adapting to observations; distinguish it from the scripted browser mode. |
| Code organization | 2 | Strong | Existing modules, tests, configuration and docs; make one primary reviewer path obvious. |
| Unit tests and judge tests | 2 | Partial | Unit tests pass; add and run semantic judge tests of agent answers/trajectories. |
| Ground-truth LLM evaluation used for tuning | 3 | Partial | Complete model and judge runs, manually inspect disagreements, document one measured improvement and a separate final check. |
| Logs and dashboard | 2 | Partial | Show actual Atlas requests in traces and a populated dashboard, including failures and cost/latency. |
| Reproducibility | 2 | Partial | Publish the local additions, verify setup from a clean clone, fix source-link placeholders and include a no-key demonstration. |

These core categories total **18 points**. Best-practice bonuses have a stated ceiling of 7, UI/cloud bonuses 3, and the supplied text mentions further manual-evaluation/feedback bonuses without their exact allocation. Those ceilings alone do not reproduce all 33 points, so this audit does not invent missing weights or award an exact present score.

**A planning target of roughly 24–27/33 is reasonable after the completion checks below**, using the core workflow, Docker/Makefile/CI, UI and human evaluation. It is not a current earned score. Cloud hosting and a runtime multi-agent architecture are not necessary to target a comfortable margin over 12. Validate the exact bonus rules against the course portal before submitting.

## Completion plan in priority order

### 1 Make the primary AI investigation demonstrable

- [ ] Keep the read-only Atlas investigation as the main capstone path. Present the older single-shot triage API and dev remediation agent as separate features, not parts of one proven workflow.
- [ ] Add an explicit user-triggered model run in the UI, or a clearly documented CLI run plus a recorded model trace accessible from the UI. Page visits must not silently incur model usage.
- [ ] Persist requested and provider-returned model IDs, prompt/version identifiers, run time, corpus/fixture hashes, parameters, output limits, usage and errors. Current Atlas output has useful trace data but lacks complete model provenance and run-level cost controls.
- [ ] Make provider timeouts/errors produce preserved failed-run records. Add a bounded output/usage budget before a batch evaluation.
- [ ] Show routing and buffer variants leading to different useful inspections, and incomplete evidence producing uncertainty rather than a guessed cause. Show at least one newly learned fact changing a subsequent query/check.

Completion evidence: three actual model traces with citations, one handled provider failure, and one reviewer command that reproduces the path. An approved capstone model budget is needed before paid runs; authorization for another project is not a capstone spending limit.

### 2 Complete evaluation of answers and tool choices

- [ ] Human-review the existing scenario keys and document known uncertainties. Retain the current automated reviews and their hash checks.
- [ ] Keep the 40-case retrieval suite, 36-case static evidence study and three-case Atlas interaction demonstration as distinct datasets with distinct claims.
- [ ] Add an opt-in answering-model runner and a separate judge runner. The existing static comparison packaging can be reused for the 36 cases; a separate trace-aware adapter is needed for Atlas.
- [ ] Judge diagnosis support, counterevidence, uncertainty, useful next checks, safety and document applicability. Also evaluate the chosen tool trajectory; do not require an exact sequence where several valid paths exist.
- [ ] Human-label a deliberately mixed sample of approximately 10–12 outputs, including errors and abstentions. Compare judge decisions with those labels and record disagreements instead of treating judge confidence as truth.
- [ ] Add a small genuine holdout from new service variants or peer-contributed cases. The four existing evaluation-candidate families have already been seen during development; do not rename them a sealed holdout.
- [ ] Record one error analysis, one justified prompt/retrieval/tool change, a development rerun and a final frozen check. Negative or mixed results are acceptable if analyzed honestly.

Primary controlled comparison: **the same model with adaptive inspection tools, with versus without knowledge retrieval**. The alert-only baseline intentionally lacks decisive evidence and should often abstain; beating it is not proof of RAG value. To claim that adaptive collection itself improves results, add a fixed-check-order comparator with the same knowledge access, or narrow the claim to demonstrated adaptive behavior.

The 36-case static study can measure how historical synopses affect answers to already supplied evidence. It cannot establish that the Atlas agent selects better tools. For broader trajectory claims, adapt an appropriate subset into separately reviewed tool-return fixtures and report that as a new dataset version. Do not turn all 100 research links into unreviewed benchmark cases.

### 3 Monitor the same workflow the reviewer sees

- [ ] Instrument Atlas investigation, model calls, inspections and retrieval with linked spans and a persistent run ID.
- [ ] Display request/failure counts, latency, model/tool calls, retrieval use, token usage and cost when prices are configured. Keep rule-based and model-driven traffic distinguishable.
- [ ] Add useful/not-useful feedback and an optional correction linked to a specific report/run ID.
- [ ] Demonstrate one failed or low-rated run becoming a human-reviewed regression example.
- [ ] Capture a dashboard and a trace from actual usage, including an insufficient-evidence case. Test the panels against emitted metrics rather than relying on dashboard JSON alone.

Use existing OpenTelemetry/Grafana plumbing. Introducing another observability vendor is unnecessary.

### 4 Package one clear submission

- [ ] Update README with the real user/problem, primary demo, rubric evidence links and explicit distinctions between offline replay, configured model, recorded results and cluster execution.
- [ ] Update current test counts and retrieval results; clearly date historical metrics. Update the source summary for incident/service knowledge and replace `YOUR_GITHUB_USER` source-link placeholders.
- [ ] Make dependency installation reproducible and verify a clean setup. `uv` is a sensible course-aligned option; no broader framework rewrite is needed.
- [ ] Run the Docker build and no-key demo, then verify the model-enabled setup separately. Initial source ingestion needs internet; do not call first-run setup fully offline.
- [ ] Add a sanitized, versioned evidence directory for evaluation summaries, selected traces and screenshots. `eval/reports/` is ignored, so local results are not automatically submission artifacts.
- [ ] Review and publish the currently uncommitted capstone changes, confirm CI at the submitted revision and rehearse a short peer demo from that revision.

Submission story: initial rollout alert → model-selected check → retrieval of the applicable service contract → contrasting observation → supported conclusion or abstention → trace and user feedback → evaluation result and one documented improvement.

## Keep outside the capstone critical path

Additional brokers, cloud migration, live production remediation, training/fine-tuning, self-hosted model serving and the financial investigator do not close the current course gaps. Neither does adding every agent pattern. A live Kubernetes read adapter can be a later extension; the current synthetic evidence replay is acceptable as a clearly labeled PoC, provided actual AI behavior and usefulness to a real user are demonstrated.
