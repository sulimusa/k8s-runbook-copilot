---
title: Lab Runbook - ResourceQuota exceeded
---
# ResourceQuota exceeded

## Symptoms
A Deployment shows fewer ready pods than desired. The ReplicaSet events contain `forbidden: exceeded quota`. Direct pod creation fails with the same message. A quota on CPU or memory can also reject pods that omit requests or limits.

## Diagnosis
1. `kubectl describe replicaset <rs-name> -n <namespace>` or `kubectl get events -n <namespace> --sort-by=.lastTimestamp` for `exceeded quota` messages.
2. `kubectl describe quota -n <namespace>` to compare `Used` with `Hard` for pods, cpu and memory.
3. `kubectl get limitrange -n <namespace>` to see whether default requests and limits are applied.

## Likely causes
- Total requests, limits or pod count in the namespace reached the hard quota.
- Pods lack the requests or limits that the quota requires.

## Remediation guidance
Reduce replicas or resource requests, remove unused workloads, or ask the cluster admin to raise the quota. Add requests and limits to pod specs or define a LimitRange with defaults. Manual, reviewed changes.

Lab evidence: `labs/scenarios/quota-exceeded`.
