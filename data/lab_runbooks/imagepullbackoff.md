---
title: Lab Runbook - ImagePullBackOff and ErrImagePull
---
# ImagePullBackOff / ErrImagePull

## Symptoms
Pod status is `ErrImagePull` and then `ImagePullBackOff`. The container never starts. Events show `Failed to pull image` followed by `Back-off pulling image`.

## Diagnosis
1. `kubectl describe pod <pod-name> -n <namespace>` and read the Events section for the exact registry error (`manifest unknown`, `unauthorized`, `not found`, timeout).
2. `kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].image}'` to confirm the image reference.
3. `kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.imagePullSecrets}'` to see which pull secrets are attached.

## Likely causes
- Typo in the image name or a tag that does not exist (`manifest unknown`, `not found`).
- Private registry without credentials: the pod needs `imagePullSecrets` (`unauthorized`, `authentication required`).
- Node cannot reach the registry: network egress, proxy, or DNS problems.
- Registry rate limiting.

## Remediation guidance
Correct the image name or tag. For private registries, create a `docker-registry` Secret in the same namespace as the pod and reference it in `imagePullSecrets` (or attach it to the service account). Verify node egress and DNS if the error is a timeout. These are manual changes to review first.

Lab evidence: `labs/scenarios/imagepull`.
