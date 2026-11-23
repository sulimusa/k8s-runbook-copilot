# Atlas API dependency troubleshooting

Fictional service guide. Status: current. Revision: dependency-v1.

Atlas API reads from a fictional catalog service and a bounded connection pool.
Dependency latency can increase request concurrency and therefore memory demand
without changing request rate. Equal requests per second alone is not proof of
equal work. Inspect request duration, inflight work and payload distributions
before declaring a new revision's memory behavior a code defect.

DNS failures, connection-pool exhaustion and readiness failures may resemble a
rollout regression but need different evidence. Historical Kubernetes incidents
are hypothesis sources only. This guide does not establish that a dependency was
slow during any specific incident; observations must support that conclusion.
Escalate absent latency or concurrency measurements rather than inventing them.
