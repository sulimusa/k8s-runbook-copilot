---
title: Lab Runbook - CrashLoopBackOff
---
# CrashLoopBackOff

## Symptoms
`kubectl get pods` shows `CrashLoopBackOff` and a growing RESTARTS count. Events contain `Back-off restarting failed container`. The container starts, exits, and the kubelet restarts it with an increasing delay between attempts.

## Diagnosis
1. `kubectl get pod <pod-name> -n <namespace>` to confirm status and restart count.
2. `kubectl describe pod <pod-name> -n <namespace>` and read `Last State`, `Reason`, `Exit Code` and the Events section.
3. `kubectl logs <pod-name> -n <namespace> --previous` to read the logs of the crashed instance (current logs may be empty because the container just restarted).
4. For multi-container pods add `-c <container-name>`.

## Likely causes
- Application error or panic at startup (exit code 1).
- Missing or wrong configuration: ConfigMap, Secret, environment variable or command/args.
- Container killed with exit code 137 (SIGKILL), often an out-of-memory kill; see the OOMKilled runbook.
- A failing liveness probe that restarts a healthy but slow container; see the probe runbook.
- A dependency (database, DNS) unavailable at startup.

## Remediation guidance
Fix the error visible in the previous logs. If the cause is configuration, correct the manifest and roll it out. If a liveness probe is too aggressive, consider a startup probe or longer timeouts. Changes are manual steps and should be reviewed before applying.

Lab evidence: `labs/scenarios/crashloop`.
