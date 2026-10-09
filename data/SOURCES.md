# Source manifest

Authoritative machine-readable version: `data/sources.yaml` (pinned commits). After `make ingest`, the exact
resolved commits and fetch times are in `data/sources.lock.json`.

| id | Repo | Pinned commit | License | Scope | Enabled |
|---|---|---|---|---|---|
| k8s-docs | kubernetes/website | `1c7aa9955e88` | CC-BY-4.0 | `tasks/debug/` + 24 targeted concept/task pages (pods, probes, scheduling, services, DNS, quotas, storage) | yes |
| k8s-runbooks | prometheus-operator/runbooks | `a685d14cf512` | Apache-2.0 | `runbooks/kubernetes/` and `runbooks/node/` | yes |
| chaos-mesh | chaos-mesh/website | `e1da01441bf5` | verify (see NOTICE) | 4 `simulate-*` pages | **no** |
| lab-runbooks | this repo | n/a | Apache-2.0 | 9 original runbooks | yes |
| lab-evidence | this repo | n/a | Apache-2.0 | output of `labs/capture.sh` (empty until you run it) | yes |

## Updating a source
1. Change `commit:` in `data/sources.yaml`.
2. `make ingest` (re-fetches, re-chunks).
3. `make eval-retrieval` and compare with the previous report. Chunk ids are path-based, so most stay stable.

## What is deliberately excluded
Private runbooks, private postmortems, customer data, vendor-proprietary docs, forum/blog scrapes of unclear license.
