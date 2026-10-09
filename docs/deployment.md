# Deployment: build once, promote the same image

```
push to main ─► verify (tests + retrieval eval gate) ─► build ONE image, tag YYYYMMDD-HHMMSS-sha ─► scan ─► push to GHCR
                                                                   │
                                          deploy that tag to dev ──┤ test in dev
                                                                   ▼
                        promote: retag the SAME digest as prod (no rebuild) ─► deploy prod ─► rollback = previous Helm revision
```
Rebuilding for prod could pull different dependency versions or corpus content than the image you tested. Promotion retags by digest instead.

## Pieces
| Artifact | What it does |
|---|---|
| `Dockerfile` | multi-stage; stage 1 builds the corpus (`make ingest` equivalent), stage 2 is a slim, non-root (uid 10001) runtime with a health check |
| `docker-compose.yaml` | Copilot + Grafana otel-lgtm for local development |
| `deploy/helm/runbook-copilot` | Deployment, Service, ConfigMap, ServiceAccount, NetworkPolicy, PodDisruptionBudget (prod); `values-dev.yaml`, `values-prod.yaml` |
| `deploy/scripts/platform-up.sh` | kind cluster, build once, load image, deploy to `dev` (always pinned to the `kind-runbook-lab` context) |
| `deploy/scripts/promote.sh` | reads the image running in dev and deploys that exact image to `prod` after a confirmation |
| `.github/workflows/ci.yml` | ruff, tests, bandit, pip-audit, retrieval eval gate, Helm lint + kubeconform, Trivy config scan |
| `.github/workflows/release.yml` | verify, build once, SBOM and provenance, Trivy image scan, push to GHCR |
| `.github/workflows/promote.yml` | manual, gated by the `production` environment: retag a tested tag as `prod` by digest |

## Run the lab
```bash
LLM_API_KEY=sk-... make platform-up     # kind + build + dev + observability backend
make promote                            # prod gets exactly the image dev runs
make rollback                           # prod back one Helm revision
make platform-down
```
Requires docker, kind, kubectl and helm. The API key is read from your environment into a Kubernetes Secret; it is never written to a values file.

## Security posture of the pod
| Control | Setting |
|---|---|
| Runs as non-root | uid/gid 10001, `runAsNonRoot` |
| Immutable filesystem | `readOnlyRootFilesystem`, writable `emptyDir` only for `/app/logs` and `/tmp` |
| No privilege escalation, no capabilities | `allowPrivilegeEscalation: false`, drop `ALL`, seccomp `RuntimeDefault` |
| No Kubernetes API access | `automountServiceAccountToken: false` (the app never talks to the API) |
| Network | NetworkPolicy: ingress only on 8000 from the release namespace, egress only DNS, HTTPS and OTLP (needs a CNI that enforces policies; kind's default CNI does not) |
| Secrets | API key from an existing Secret via `secretKeyRef` |
| Availability | PodDisruptionBudget and 2 replicas in prod |

## Scan results (Trivy 0.75.0 misconfiguration scan, run locally)
- Dockerfile: 27 checks passed, 0 failures.
- Helm chart (dev and prod values): all templates render; 3 findings, accepted and documented in `.trivyignore`:
  KSV-0011 (no CPU limit, deliberate: avoids throttling a latency-sensitive service; memory limit and CPU request are set),
  KSV-0110 (default namespace, raised only when scanning without a release namespace), KSV-0125 (registry allow-list policy is organisation specific).
- `deploy/k8s/observability.yaml` has 13 findings by design: it is a lab-only manifest around an upstream demo image and is excluded from the CI scan. Never expose it.
- `bandit`: no issues. `pip-audit`: no known vulnerabilities in the resolved dependencies.

## What was and was not verified
Verified where this was written: the Helm chart renders under the real Helm libraries (via Trivy), the Dockerfile and chart scans above,
bandit, pip-audit, ruff, 69 tests, YAML syntax of the workflows, compose and manifests, shell syntax of the scripts.
**Not run there:** `docker build`, the kind deployment, `helm lint`/kubeconform, the GitHub workflows, the Grafana dashboard and alerts against live data,
and the Trivy *image* vulnerability scan (needs the vulnerability database). Run `make platform-up` and push to GitHub once; expect to fix small things,
then update this section with what you actually saw.
