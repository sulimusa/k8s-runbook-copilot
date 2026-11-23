# Capstone criteria: current evidence map

Reviewed November 23, 2026. **The local historical-investigation capstone covers the core course criteria.** The submission still needs the tested release published to GitHub and the course form submitted. The [submission guide](submission.md) is the current checklist; the [earlier audit](course-alignment-2026-11-04.md) is historical, not current status.

The course source is [AI Engineering Buildcamp code](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code). Its [evaluation guide](https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/main/documentation-agent/evals/README.md) distinguishes human-label and synthetic workflows; this project makes that distinction too. Point ceilings below are from the rubric supplied by the student, not independently inferred from the public code. This is a self-assessment, not a grading promise.

## Five engineering steps

| Step | Evidence |
|---|---|
| Real problem / real user | A DevOps engineer needs to connect retained cluster changes with applicable operating procedures. The project owner confirmed the OOM/RAG next checks were helpful; [exact feedback](user-feedback.json) is one usefulness observation, not an accuracy study. |
| Simple working PoC | [Chat](../app/ui.py), bounded history/current/runbook tools, three no-key recorded demos, isolated optional live collector. |
| Improve through tests/debugging | Unit/integration tests, strict output and citation validation, [specific answer and judge failures](judge-reliability.md), preserved failed attempts, targeted regression tests. |
| Monitoring / usage data | History reports store calls, tokens, costs, tool traces and new end-to-end timing. The UI's **Monitoring & feedback** view shows real saved runs and explicit user feedback; bundled synthetic and local collected runs are distinguished. |
| Evaluation dataset / tuning | [24-case study](knowledge-value-evaluation.md) with 72 model answers and separate judge reviews; [three-case historical comparison](history-demo.md); scoped retrieval evaluation and [31 adjudicated findings](judge-adjudications.json). The reserved set is author-aware; the three demos were reused in development. |

## Rubric map

| Criterion | Conservative self-assessment | Where to inspect |
|---|---:|---|
| Problem description | 2/2 | README first section, user-feedback.json |
| Knowledge base / retrieval | 2/2 | `ingest/`, `retrieval/`, version/environment-scoped synthetic contracts; [retrieval results](knowledge-value-retrieval-results.json) |
| Agents / LLM tools | 3/3 | `history/chat.py`: model-selected history, current-state and runbook reads, bounded iterations, structured finish; actual traces in history-demo-results.json |
| Code organization | 2/2 | `src/runbook_copilot`, `app`, `tests`, `eval`, `docs` |
| Unit and judge tests | 2/2 | `tests/`; [nine recorded judge controls](history-judge-controls.json), actual answer reviews, independent prompts (not independent human review) |
| Evaluation used for tuning | 2–3/3 | Original vs corrected outputs, scope filtering, false-positive judge analysis, explicit developer adjudications and separate user feedback |
| Monitoring: logs + dashboard | 2/2 | **Monitoring & feedback**, `history/monitoring.py`, saved per-run evidence; selected-run costs exclude judges and do not pretend to be whole-account totals |
| Reproducibility | 2/2, clean install verified | `uv.lock`, no-key default demo, Makefile, Dockerfile.capstone, offline artifact checks |
| Coding-practice bonus | Credit for Docker, Makefile, locked uv and CI configuration | Tooling exists; published CI at the final revision remains a release check. Exact bonus allocation belongs to graders. |
| UI / deployment bonus | UI demonstrated; no cloud-deployment claim | Streamlit; local Docker and optional dedicated Kubernetes lab. |
| Human evaluation / feedback bonus | One owner usefulness review, not broad ground-truth validation | user-feedback.json; feedback download creates a **pending** evaluation candidate. |

Core subtotal: approximately **17–18/18** if the reviewer reproduces the evidence. A cautious overall expectation is **22–25/33**, with uncertainty in bonus allocation and evaluator judgment. The 12-point passing threshold should have leeway; no grade is guaranteed.

## Why RAG and agents are justified

History tools retrieve cluster-specific observations that a general model does not possess. RAG supplies service/version-specific operating semantics that those observations alone cannot reveal. In the OOM demo it adds effective worker/cache-setting and allocation checks; in the selector and missing-history controls it adds no necessary causal evidence. The claim is better-targeted investigation in a particular example, not universal superiority.

The agent uses structured JSON action dispatch. It is a genuine model-selected loop, though it does not use provider-native tool-call messages. Multiple runtime agents, fine-tuning, cloud migration and a larger vector database are not necessary to complete this capstone.

## Limits to state explicitly

- Fictional snapshots demonstrate mechanics; they are not evidence of production effectiveness.
- The judge still produces false positives after passing controls. Developer decisions are not independent human labels.
- One positive owner response is not a measured productivity improvement.
- Historical coverage begins when collection starts; baselines are not deployment dates.
- Production remains read-only. One explicit guarded dev selector repair is optional and not part of the recorded demos.
- New held-out cases and independent peer review would strengthen the work, but do not require expanding the PoC before submission.
