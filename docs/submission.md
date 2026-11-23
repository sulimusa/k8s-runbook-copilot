# Reviewer start here

## What this project does

Kubernetes Runbook Copilot helps an engineer investigate **what changed before an incident**. It combines retained cluster history, collected current state and applicable operational documents, then returns a cited timeline, hypotheses, missing evidence and a safe next check. Production is read-only; the optional isolated dev lab exposes one separately approved selector restoration.

The first user is the project owner, a DevOps engineer. Their [recorded feedback](user-feedback.json) says the OOM/RAG next checks were helpful. This establishes one concrete user interaction, not production adoption or a controlled usefulness study.

## Run the demo without a key or cluster

Prerequisites: Python 3.11+ (3.12 recommended), Git and [uv](https://docs.astral.sh/uv/). Installation downloads dependencies; once installed, recorded demos need no API key, corpus download or Kubernetes cluster.

```sh
git clone https://github.com/sulimusa/k8s-runbook-copilot.git
cd k8s-runbook-copilot
uv sync --locked --all-extras
uv run --frozen --all-extras streamlit run app/ui.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

Open <http://127.0.0.1:8501>. **Three capstone demos** is the default. Expand **Recorded model comparison — no API call**. These are actual saved model outputs, not newly generated answers or a deterministic planner pretending to be an LLM.

Choose **Monitoring & feedback** to inspect the six bundled runs, model/tool calls, tokens, provider latency, known cost and traces. Local recorded runs show failures as well as successes. New investigations also have end-to-end timing. Earlier snapshots are not assigned invented timestamps or durations.

Alternatively, build a no-key container:

```sh
docker build -f Dockerfile.capstone -t k8s-runbook-capstone:review .
docker run --rm --name k8s-capstone-review -p 127.0.0.1:18501:8501 k8s-runbook-capstone:review
```

Open <http://127.0.0.1:18501>. This image contains only the packaged app, original synthetic fixtures and reviewer reports. It has no credentials, cluster configuration or downloaded corpus. Feedback in a disposable container disappears when removed unless `/app/logs` is persisted.

## Check the package

```sh
uv run --frozen --all-extras ruff check src app eval tests analysis observability scripts
uv run --frozen --all-extras pytest -q
uv run --frozen --all-extras python scripts/check_submission.py
```

These checks do not spend API credits. Tests that create feedback use temporary databases; they do not count as human reviews. The artifact check validates recorded answer/review hashes, six run traces, citation timestamps, arm isolation and the broader evaluation dataset.

To generate new answers, configure a local `.env` from `.env.example` with your own key, model, prices and explicit campaign budget. The budget is a persistent ledger, not a per-request allowance. The author's $6 allowance is nearly consumed; do not reset it to rerun this demo. For live history, follow [collector setup](cluster-history.md). The demo image itself cannot access the host collector or corpus.

## Five-minute review

Follow [demo-script.md](demo-script.md). The three outcomes are:

1. **OOM after rollout:** RAG adds service-specific worker/cache checks, without proving actual allocation or root cause.
2. **Selector mismatch:** observations already identify the mechanism; RAG is not necessary.
3. **Earlier outage:** neither approach can reconstruct missing history; causal attribution and rollback justification are withheld.

Then inspect [judge reliability](judge-reliability.md). All raw ratings are preserved alongside explicit developer adjudications. A judged pass is not assumed to mean correctness.

## Evidence map

- [Current course criteria and cautious score estimate](course-alignment.md)
- [Three-case results and limitations](history-demo.md)
- [Actual final model answers](history-demo-results.json) and [bound review decisions](history-demo-adjudications.json)
- [24-case evaluation protocol](knowledge-value-evaluation.md) and [recorded outcomes](knowledge-value-results.md)
- [Prior disputed findings, all adjudicated](judge-adjudications.json)
- [Owner usefulness feedback](user-feedback.json)
- [Local verification report](submission-verification.json), updated after final checks

## Before submitting

- The capstone is published on `main`. Use a specific commit link when submitting, so reviewers can reproduce the same revision.
- Confirm [GitHub Actions](https://github.com/sulimusa/k8s-runbook-copilot/actions) is green for that exact commit. The local verification report records pre-publication checks and does not replace hosted CI.
- Submit the course form and any required video through the student's account. This task does not submit the form or invent portal requirements/deadlines.

Optional strengthening: independent peer labels on new cases and a short recorded walkthrough. The included script and recorded demo make a live presentation possible without additional model spending. Independent human correctness validation and cloud deployment are not claimed.
