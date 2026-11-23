# Atlas asynchronous worker capacity

Fictional service documentation. Status: current. Revision: worker-v1.
Applies only to the atlas-worker Deployment and its queue consumers.

Worker pods have a 2048 MiB reference memory limit and batch-oriented result
buffers. They receive queue messages, not HTTP traffic from the public atlas-api
Service. Worker capacity values must not be applied to API pods even though the
two workloads share a namespace and some libraries. Worker readiness indicates
consumer initialization rather than eligibility for public HTTP routing.

For worker memory pressure, inspect batch size, inflight messages and retry queues.
For API memory pressure, consult the API operating envelope and public Service
routing contract instead. Similar document vocabulary is not evidence that the
same remedy applies. Record the workload identity before using a sizing rule.
