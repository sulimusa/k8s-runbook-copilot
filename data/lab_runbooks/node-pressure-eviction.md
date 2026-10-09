---
title: Lab Runbook - Node pressure and pod eviction
---
# Node pressure and eviction

## Symptoms
Pods show status `Evicted` (phase `Failed`). Nodes report conditions `MemoryPressure`, `DiskPressure` or `PIDPressure`. New pods may stay Pending because the node is tainted for pressure.

## Diagnosis
1. `kubectl describe node <node-name>` and read `Conditions` and recent Events.
2. `kubectl get pods -A --field-selector=status.phase=Failed` to list evicted pods, then `kubectl describe pod <pod-name>` for the eviction message.
3. `kubectl top node` to see current CPU and memory use (needs metrics-server).
4. `kubectl get events -A --sort-by=.lastTimestamp` for eviction events.

## Likely causes
- Node memory or ephemeral storage consumed by pods without limits.
- Container logs or images filling the node disk.
- Too many processes on the node (PID pressure).

## Remediation guidance
Set realistic requests and limits so the scheduler places pods sensibly and eviction ranks them correctly. Free disk space, clean unused images, or add node capacity. Cleaning up evicted pods and node changes are manual, reviewed steps.

Note: this scenario is hard to reproduce safely on a laptop kind cluster; the runbook is derived from the public Kubernetes documentation on node-pressure eviction.
