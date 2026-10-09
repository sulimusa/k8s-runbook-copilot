# Third-party content and attribution

This project's **code** is Apache-2.0 (see `LICENSE`). The **corpus** it retrieves from is third-party content,
fetched at build time (not committed) and surfaced as short cited excerpts. Pinned commits are in `data/sources.yaml`
and `data/SOURCES.md`.

| Source | Owner | License | Changes made |
|---|---|---|---|
| Kubernetes documentation (`kubernetes/website`, `content/en/docs`) | © The Kubernetes Authors | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Converted to plain markdown (Hugo shortcodes and comments removed), split into chunks, excerpts shown in answers with a link to the original page. |
| Prometheus Operator runbooks (`prometheus-operator/runbooks`, the kubernetes-mixin / kube-prometheus alert runbooks) | © The Prometheus Operator Authors | Apache-2.0 | Chunked; excerpts shown in answers with a link to the original page. |
| Chaos Mesh docs (`chaos-mesh/website`) | © Chaos Mesh Authors | Apache-2.0 (**verify**; disabled by default) | Not included unless you enable it in `data/sources.yaml`. |
| `data/lab_runbooks/`, `data/lab_evidence/` | This project | Apache-2.0 | Original work, written from public documentation and local lab output. |

Kubernetes is a registered trademark of The Linux Foundation. This project is not affiliated with or endorsed by
the Kubernetes project, the CNCF, or any other source owner.
