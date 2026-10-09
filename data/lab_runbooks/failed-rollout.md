---
title: Lab Runbook - Deployment rollout stuck or failed
---
# Failed or stuck rollout

## Symptoms
`kubectl rollout status deployment/<name>` hangs or reports `Waiting for deployment ... rollout to finish`. After the progress deadline the Deployment condition `Progressing` becomes `False` with reason `ProgressDeadlineExceeded`. Old pods keep running while new pods do not become Ready.

## Diagnosis
1. `kubectl rollout status deployment/<name> -n <namespace> --timeout=30s`.
2. `kubectl describe deployment <name> -n <namespace>` and read Conditions and Events.
3. `kubectl get rs -n <namespace>` to compare the new and old ReplicaSets.
4. `kubectl get pods -n <namespace>` and `kubectl describe pod <new-pod>` to see why new pods are not Ready (image pull errors, failing probes, insufficient resources, quota).
5. `kubectl rollout history deployment/<name> -n <namespace>`.

## Likely causes
Bad image tag, failing readiness probe, insufficient cluster resources, exceeded quota, or a crashing new version. Kubernetes does not roll back automatically when the deadline is exceeded.

## Remediation guidance
Fix the underlying cause in the new pods. If the new version is bad, rolling back with `kubectl rollout undo` is a manual change to perform after review.

Lab evidence: `labs/scenarios/failed-rollout`.
