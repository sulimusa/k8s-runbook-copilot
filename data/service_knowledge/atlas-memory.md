# Atlas API memory and concurrency operating envelope

Fictional service documentation. Status: current. Revision: capacity-v2.
Applies to Atlas API HTTP pods at the reference payload distribution, not workers.

The validated reference envelope is 80 requests per second per ready pod, a 512 MiB
container limit and `RESULT_BUFFER_MIB=64`. These are fictional workload-specific
values, not general Kubernetes sizing advice. Each active HTTP request can retain
a result buffer; increasing that buffer changes memory demand even without a leak.

During OOM investigation compare old and new pods at comparable request rates,
payload size and concurrency. Check the effective result-buffer setting rather
than assuming the deployment manifest is the whole configuration. If old and new
pods have similar load but the new revision allocates substantially more memory,
inspect configuration changes and allocation profiles. Do not label an allocation
regression a memory leak without time-series or heap evidence of retained growth.

If traffic exceeds the reference envelope on only a subset of ready replicas,
investigate routing and load distribution first. Increasing the memory limit may
mask the imbalance. The approved envelope can change after load testing; record
its revision and applicability in any recommendation.
