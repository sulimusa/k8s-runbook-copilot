# Atlas API routing contract

Fictional service documentation. Status: current. Revision: routing-v3. Applies to
Atlas API HTTP traffic in namespace atlas-demo, not to its asynchronous workers.
Owner: fictional Atlas platform team. Effective date: 2026-10-01.

The public atlas-api Service selects `app=atlas-api`. Release identity belongs on
pod labels for observability, not on this Service selector. During a rolling update,
both old and new ready replicas must be eligible for public traffic. A separate
canary Service may deliberately select a release; do not confuse it with atlas-api.

To investigate rollout-related errors, compare the observed Service selector, pod
labels, EndpointSlice membership and per-pod request rates over the same interval.
A release selector on the public Service violates this contract. It does not by
itself prove why a container exhausted memory: examine the traffic and memory
evidence before attributing the OOM. A normal selector also does not rule out every
network failure. Escalate inaccessible endpoint or traffic telemetry explicitly.

Any routing change requires an owner-reviewed proposal and a rollback plan. This
investigation assistant reads evidence and recommends checks; it does not change routing.
