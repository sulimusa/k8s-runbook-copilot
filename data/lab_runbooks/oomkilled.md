---
title: Lab Runbook - OOMKilled (container memory limit)
---
# OOMKilled

## Symptoms
A container restarts repeatedly. `kubectl describe pod` shows `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`. The pod may also show CrashLoopBackOff.

## Diagnosis
1. `kubectl describe pod <pod-name> -n <namespace>` and look for `Reason: OOMKilled` and the configured `Limits` and `Requests` for memory.
2. `kubectl logs <pod-name> -n <namespace> --previous` for application messages before the kill.
3. `kubectl top pod <pod-name> -n <namespace> --containers` to compare live usage with the limit (needs metrics-server).
4. `kubectl get events -n <namespace> --sort-by=.lastTimestamp` for recent kill and restart events.

## Likely causes
- The memory limit is lower than what the application needs.
- A memory leak or an unbounded cache or batch size.
- Several processes in one container sharing a small limit.

## Distinguish from node-pressure eviction
A container exceeding its own memory limit is killed by the kernel (`OOMKilled`). Node-level memory pressure instead makes the kubelet evict whole pods (status `Evicted`); see the node pressure runbook.

## Remediation guidance
Consider raising the memory limit (and request) to match measured usage, or fix the leak. Treat limit changes as manual, reviewed changes.

Lab evidence: `labs/scenarios/oomkilled`.
