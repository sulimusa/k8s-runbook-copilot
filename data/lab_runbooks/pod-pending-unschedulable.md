---
title: Lab Runbook - Pod stuck Pending (FailedScheduling)
---
# Pod stuck in Pending

## Symptoms
The pod stays `Pending` with no node assigned. Events show `FailedScheduling` with a message such as `0/3 nodes are available: ...`.

## Diagnosis
1. `kubectl describe pod <pod-name> -n <namespace>` and read the `FailedScheduling` event: it lists why each node was rejected.
2. `kubectl get nodes` and `kubectl describe node <node-name>` to compare `Allocatable` with `Allocated resources`, and to read node taints.
3. `kubectl get pvc -n <namespace>` if the pod mounts volumes: an unbound PersistentVolumeClaim keeps the pod Pending.

## Reading the scheduler message
- `Insufficient cpu` or `Insufficient memory`: requests exceed free capacity on every node.
- `node(s) had untolerated taint`: the pod lacks a matching toleration.
- `node(s) didn't match Pod's node affinity/selector`: nodeSelector or affinity matches no node.
- `pod has unbound immediate PersistentVolumeClaims`: storage is not provisioned or bound.

## Remediation guidance
Reduce the pod's resource requests, add cluster capacity, add the needed toleration, correct nodeSelector or affinity, or fix the PVC and StorageClass. All of these are manual changes to review first.

Lab evidence: `labs/scenarios/pending-unschedulable`.
