---
title: Lab Runbook - Readiness and Liveness probe failures
---
# Probe failures

## Symptoms
- Readiness failing: pod is `Running` but `READY 0/1`; it is removed from Service endpoints and receives no traffic. Events: `Readiness probe failed`.
- Liveness failing: the container is restarted repeatedly. Events: `Liveness probe failed` then `Container ... failed liveness probe, will be restarted`.

## Diagnosis
1. `kubectl describe pod <pod-name> -n <namespace>` and read the probe definition and the probe failure events (for example `connection refused` or `HTTP probe failed with statuscode: 404`).
2. `kubectl logs <pod-name> -n <namespace>` to see whether the application is listening on the probed port and path.
3. `kubectl get endpoints <service-name> -n <namespace>` to confirm a not-ready pod is excluded.

## Likely causes
- Probe targets the wrong port or path.
- Application slower to start than `initialDelaySeconds` and `failureThreshold` allow; a liveness probe then kills it before it is ready.
- Probe `timeoutSeconds` too short for a loaded app.
- Health endpoint depends on an unavailable downstream service.

## Remediation guidance
Correct the port and path. For slow starters consider a `startupProbe` so liveness checks only begin after startup. Tune `timeoutSeconds` and thresholds. Manual, reviewed change.

Lab evidence: `labs/scenarios/probe-failure`.
