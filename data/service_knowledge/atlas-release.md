# Atlas API release investigation procedure

Fictional procedure. Status: current. Revision: release-v4. Applies to atlas-demo.

Record the first failure timestamp and compare it with ReplicaSet creation,
effective configuration and routing changes. Temporal correlation narrows the
search; it does not establish causality. Preserve observations before proposing
restarts because previous-container logs and short-lived events may be lost.

Collect rollout state first, then choose a discriminating check. OOMKilled across
new replicas can reflect uneven routing, larger per-request buffers, a leak or
node-level pressure. After learning a new configuration key or selector value,
search the service documents again using that detail. Do not repeatedly retrieve
the same generic OOM explanation when a targeted service contract is available.

A final investigation should separate observations, documentary constraints,
hypotheses ruled out, missing information and the next owner-approved action.
Rollback is not automatically safe: verify compatibility and capture the
configuration diff. The assistant must not claim a recommendation was applied.
