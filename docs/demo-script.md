# Five-minute walkthrough

**0:00–0:40 — Problem.** “I need to investigate what changed before a Kubernetes failure. A generic model may know Kubernetes, but it does not know my retained cluster history or the operating contract for this service version.” Explain that the demo snapshots are fictional and fixed; the recorded answers came from actual model calls.

**0:40–1:50 — Where RAG helps.** Open the OOM comparison. Both arms observe the rollout, unchanged 512 MiB limit, three restarts and the last OOMKilled termination. The RAG arm retrieves four workers × 192 MiB cache budgets and asks to inspect effective settings and actual allocation. Point out that potential allocation is not measured use and prior restart causes remain unknown. Show the retrieved contract and tool trace.

**1:50–2:30 — Where RAG adds little.** Select the Service-selector case. Show the changed selector, current Pod labels and empty endpoints. Both arms identify the mismatch. Explain why generic guidance does not supply the decisive evidence here.

**2:30–3:05 — When the assistant should stop.** Select the earlier-outage case. Collection started after the requested incident. Both arms request historical evidence and decline to justify rollback. A baseline is first observation, not deployment time.

**3:05–4:10 — Evaluation and debugging.** Expand judge findings and developer review. Explain one false positive: the judge treated a qualified hypothesis as a proven claim. Explain one real solver defect: restart count was incorrectly treated as repeated proven OOM events. Show the regression test and preserved failed attempt. Mention the broader 24-case study; do not present the reused three demos as held-out evaluation.

**4:10–4:45 — Monitoring and feedback.** Open Monitoring & feedback. Show calls, tokens, costs and a report trace. Feedback is linked to an exact answer hash. An export is a pending ground-truth candidate, never automatically a gold answer. State that the owner found the OOM checks useful; do not claim measured time savings.

**4:45–5:00 — Reproduction and limits.** Show the locked setup, tests and Docker command. Production is read-only; no repairs ran during these demos. Closing claim: “Operational knowledge improved the specificity of next checks in this example; evidence and honest uncertainty remain necessary.”
