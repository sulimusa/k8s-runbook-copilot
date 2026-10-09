# Lab scenarios

Disposable failure scenarios used to generate **my own evidence** for the corpus (and eval cases).

```bash
kind create cluster --name runbook-lab --config labs/kind-config.yaml   # or k3d / minikube
make lab SCENARIO=crashloop          # applies manifest, waits, captures evidence, deletes namespace
make ingest                          # picks up data/lab_evidence/**/evidence.md
```

| Scenario | Failure produced | Category |
|---|---|---|
| `crashloop` | container exits 1 at startup | CrashLoopBackOff |
| `imagepull` | image tag does not exist | ImagePullBackOff |
| `oomkilled` | 250M allocation vs 100Mi limit | OOMKilled |
| `pending-unschedulable` | requests 64 CPU / 512Gi | PodPending |
| `probe-failure` | wrong readiness port + bad liveness path | ProbeFailure |
| `dns-service` | Service selector typo (no endpoints) | DNSServiceConnectivity |
| `failed-rollout` | v2 image does not exist, 30s deadline | FailedRollout |
| `quota-exceeded` | ResourceQuota pods=2, replicas=4 | ResourceQuotaOrNodePressure |

Node pressure (disk/memory) is not simulated: it is unsafe on a laptop cluster, so that category relies on the
public docs and `data/lab_runbooks/node-pressure-eviction.md`.

Safety: `capture.sh` refuses to run on any context except kind/k3d/minikube and only deletes the namespace it created.
Review each `evidence.md` before committing (no secrets, no real hostnames).
