# Atlas API telemetry interpretation

Fictional operations guide. Status: current. Revision: telemetry-v2.

Use matching time windows for request rate, memory, rollout and endpoint observations.
The replay demo exposes normalized measurements; these are synthetic observations,
not verbatim Prometheus or kubectl output. Every observation has an ID and timestamp.

A failed query or unavailable metric is unknown, not zero. Missing per-pod request
rates prevent confirming a traffic-concentration hypothesis. Kubernetes current
metrics alone may miss a pre-crash peak; prefer a bounded window including the last
termination. No positive trend can be inferred from a single memory sample.

If telemetry is unavailable, retain the competing explanations and identify which
measurement would separate them. Do not infer that old pods received traffic simply
because they are Ready. Endpoint eligibility and actual routing volume are distinct
facts. An investigation may conclude that a service contract is violated while
leaving the precise OOM mechanism unresolved.
