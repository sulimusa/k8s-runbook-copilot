---
title: Lab Runbook - Service unreachable, no endpoints, DNS resolution
---
# Service connectivity and DNS

## Symptoms
Requests to a Service time out or are refused, or a client cannot resolve the Service name.

## Diagnosis
1. `kubectl get svc <service-name> -n <namespace> -o wide` to see the selector and ports.
2. `kubectl get endpoints <service-name> -n <namespace>`: an empty list (`<none>`) means no ready pod matches the Service selector.
3. `kubectl get pods -n <namespace> --show-labels` and compare labels with the Service selector. A typo in either side is a common cause.
4. Check pods are Ready (`kubectl get pods`) and that the Service `targetPort` matches the container port.
5. For name resolution: `kubectl get pods -n kube-system -l k8s-app=kube-dns` and `kubectl logs -n kube-system -l k8s-app=kube-dns` to check CoreDNS health.
6. `kubectl get networkpolicy -n <namespace>` to see whether a policy could block the traffic.

## Likely causes
- Selector does not match pod labels (no endpoints).
- Pods not Ready (failing readiness probe), so they are excluded from endpoints.
- Wrong `targetPort`.
- CoreDNS pods unhealthy, or the client uses a wrong or cross-namespace name (use `<svc>.<namespace>`).
- A NetworkPolicy blocks ingress or egress, including DNS to kube-system.

## Remediation guidance
Align labels and selector, fix ports, resolve readiness failures, restore CoreDNS, or adjust NetworkPolicy. Manual changes to review first. Running a throwaway debug pod to test DNS (`nslookup`) is a manual step, not a read-only diagnostic.

Lab evidence: `labs/scenarios/dns-service`.
