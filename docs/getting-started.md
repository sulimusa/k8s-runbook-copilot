# Getting started

## Local demo

Install Python 3.11+ (3.12 recommended), Git and [uv](https://docs.astral.sh/uv/), then run:

```sh
git clone https://github.com/sulimusa/k8s-runbook-copilot.git
cd k8s-runbook-copilot
uv sync --locked --all-extras
make demo
```

Open <http://127.0.0.1:8501>. The default **Recorded investigations** view contains three fictional snapshots and saved outputs from actual model runs. Expand **Recorded model comparison — no API call** to compare evidence-only and RAG answers. Installation needs internet access; browsing the installed demo does not need a model key, downloaded corpus or cluster.

The [walkthrough](demo-script.md) explains the cases. **Monitoring & feedback** displays calls, tokens, costs, traces and feedback linked to an exact answer. Older reports without timing or cost fields show unknown values rather than invented measurements.

## Docker

```sh
docker build -f Dockerfile.demo -t k8s-runbook-copilot:demo .
docker run --rm --name runbook-demo -p 127.0.0.1:18501:8501 k8s-runbook-copilot:demo
```

Open <http://127.0.0.1:18501>. The image bundles the app, synthetic fixtures and recorded answers. It contains no model credentials or cluster configuration. Feedback in a disposable container disappears when it is removed unless `/app/logs` is persisted.

## Generate a new investigation

Copy `.env.example` to `.env` and configure your approved model endpoint, key, token prices and campaign budget. Keep `.env` private. The budget ledger persists across runs; it is not a per-request allowance. Starting a new model investigation is an explicit UI action and may incur provider charges.

For the live workflow, build the retrieval corpus with `make ingest`, then follow [collector setup](cluster-history.md#reproduce-locally). Choose **Live cluster history** in the UI. The demo container alone does not connect to the host collector or corpus.

Production-mode access is read-only. The optional dev selector repair requires a separate restricted identity and explicit review.

## Validate your installation

```sh
make demo-check
```

This runs lint, tests and recorded-artifact integrity checks without model calls or Kubernetes access. The integrity check verifies answer/review hashes, citation timestamps and separation of evaluation answer keys from retrieval. Tests use temporary feedback databases.

See [CI results](https://github.com/sulimusa/k8s-runbook-copilot/actions), [evaluation results](history-demo.md) and [known judge limitations](judge-reliability.md).
