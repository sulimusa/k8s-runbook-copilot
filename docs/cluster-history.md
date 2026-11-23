# Cluster history → conversational investigations

This is the capstone's live-cluster path. The Atlas cases remain regression fixtures, not a substitute for collected cluster evidence.

## Scope and isolation

- Dedicated kind cluster: `runbook-capstone`, one control-plane and one worker.
- Separate Kubernetes API, kubeconfigs, service accounts and history PVC. Nothing mounts or queries the financial project or `sre-ai-mvp`.
- Namespaces: `dev-capstone` and `prod-capstone`. Both contain synthetic demo workloads; `prod-capstone` is a production-mode policy demonstration, not a real production environment.
- Collector in `copilot-system`, one replica, SQLite WAL on a 1 GiB PVC. History is retained for 30 days. Keep the cluster running to accumulate history; stopping the laptop/cluster interrupts collection. Deleting the cluster destroys this local volume.
- Chat: <http://127.0.0.1:8501>. Read-only history API: <http://127.0.0.1:8011/docs>.

## What is collected

The collector lists and watches Pods, Deployments, ReplicaSets, Services, EndpointSlices and core Kubernetes Events in the two allowed namespaces. It stores allowlisted projections, before/after changes, observation time, resource UID/version and per-stream watch checkpoints. Resource names reused with new UIDs remain distinct.

Watch checkpoints and changes commit together. Repeated versions are deduplicated. Semantically identical updates advance the checkpoint without adding duplicate timeline entries. Startup inventories are labelled `BASELINE`, never a historical deployment. Resumption after restart is recorded as an interruption; expired watches trigger a relist labelled `RECONCILED`. Relisting cannot recover intermediate changes that the API no longer retains.

Coverage includes start time, per-stream heartbeats, errors and recent interruptions. “Last month” means query the retained records in that interval, **not** claim that a month has already been collected. Current state is the most recently collected state, not a fresh Kubernetes read performed by chat. The UI warns when streams are missing or older than 75 seconds.

Not collected yet: audit actors, Helm/Argo/Git commit metadata, ConfigMap contents, environment values, logs, metrics, all resource kinds, or the full API object. Even labels are restricted to the demo's routing labels. Event reasons are retained; free-text Event messages are omitted. Arbitrary Service selector keys are marked incomplete and cannot be used for restoration.

## How the agent investigates

1. Scope is selected by the user: cluster, namespace and 1/7/30-day window.
2. Chat receives coverage and a recent-record summary.
3. The LLM chooses bounded read tools: targeted history with before/after state, current observations, and runbook retrieval from the existing corpus.
4. The final answer cites retrieved history/current/runbook IDs and distinguishes observation from probable explanation. Invalid tool choices and citations are rejected. Text inside collected records and documents is untrusted input.
5. Tool choices, evidence, model usage and answers are saved to ignored `logs/history-chat/`. Conversation context stays within the selected scope and resets when scope changes. The chat session itself is not a durable conversation database.

The host-side chat uses the existing bounded OpenAI client and its persistent campaign budget. No API key is copied into the collector image, Kubernetes manifests or cluster. The user-approved $6 total cap is shared with Atlas and comparison tests; exhaustion blocks calls rather than silently increasing it. Existing spend is preserved.

This is an agent with retrieval and multiple read tools. Citation membership checks do not prove that an explanation is correct. The new live-history path still needs its own held-out evaluation and judge calibration; the existing 36 scenarios and Atlas judge results are separate evidence.

## Investigation guidance adapted from the supplied SRE definition

On November 6, 2026, the live chat instructions were strengthened using the SRE definition
shared by the user: establish impact and incident scope, test competing explanations, state
missing access, and accompany mitigation proposals with risks, verification and rollback/stop
conditions. Unknown customer impact stays unknown. Confidence is qualitative, not calibrated.
The report records an instruction version and hash of the exact system prompt used.

This is a local instruction change, not an OpenAI Agents API migration, model change or new
integration. The existing read tools and independently enforced repair boundary are unchanged.
The November 22 history-sre-v4 flow has paired paid runs on the [three synthetic history demos](history-demo.md), plus a read-only live smoke check. These are development checks, not held-out evidence.
The frozen 24-case study prompts are unchanged; their comparison is separate from live chat.

The supplied export configured web search; it did not show a connected cluster history or
private runbook retrieval tool. That is a property of that configuration, not a platform limit.
OpenAI supports [custom tools and MCP](https://developers.openai.com/api/docs/guides/tools)
and [retrieval over files](https://developers.openai.com/api/docs/guides/tools-file-search).
An agent given equivalent evidence, tools and policies could offer similar functionality.

Our potential value is the integrated Kubernetes workflow: retained before/after history with
coverage disclosure, targeted read tools, applicable operational guidance, evidence references,
and a narrowly controlled dev repair. RAG alone is not a unique advantage. The 24-case study
measures scope-filtered service knowledge in a frozen evaluation; that filtering is not yet a
general service-version filter in the live chat retriever. Logs/metrics connectors are still
absent. Do not present either capability as complete.

## Dev repairs and production read-only

Chat has no mutation tool. The separate **Restore previous selector in dev** button is the first live repair:

- Only `dev-capstone/demo-web` may be patched by the interactive identity.
- Uses a prior complete selector in a stored Service change, not a model-generated patch.
- Checks cluster UID, namespace opt-in, dev policy, existing matching pods, Service UID and resource version.
- Performs a server dry run, then a conditional JSON patch.
- Verifies ready EndpointSlice endpoints. If verification fails, attempts a conditional rollback; concurrent changes prevent automatic rollback and require review.
- Verification is endpoint readiness, not an end-to-end HTTP transaction or proof of business recovery.
- An audit result is saved in ignored `logs/history-repairs.jsonl`.

Production has no write identity, no Apply control, and the repair function rejects its namespace before calling Kubernetes. The collector itself has no patch/delete rights in either environment. The restricted host dev credential expires after eight hours; rerunning the installer refreshes it without printing it. The in-cluster collector uses its automatically rotated ServiceAccount token.

## Reproduce locally

From the repository root (activate `.venv` first):

```sh
pip install -e '.[app,kube,otel,dev]'
mkdir -p .agent
kind create cluster --name runbook-capstone --image kindest/node:v1.37.0 \
  --config deploy/history/kind.yaml --kubeconfig .agent/capstone-admin.kubeconfig --wait 120s
make history-image
make history-install
make history-demo
# If the public knowledge corpus is not already built:
make ingest
make history-chat
```

Do not recreate an existing cluster. The explicit kubeconfig avoids changing the operator's default context. Port 8011 must be free before cluster creation. Docker images are built and loaded locally; no registry publication is required.

Create a bounded demo fault **only in the dev lab**:

```sh
kubectl --kubeconfig .agent/capstone-admin.kubeconfig -n dev-capstone \
  patch service demo-web --type=merge \
  -p '{"spec":{"selector":{"app":"no-matching-pods"}}}'
```

Ask: “Why does demo-web have no endpoints? Compare recent Service changes, current pod labels and endpoints.” Inspect the cited changes, then use the dev restore button. Select `prod-capstone` to see the read-only boundary. To ask about the prior outage after recovery, say “What caused the earlier endpoint outage, and is it recovered now?”

## Remaining limits

This is a single-user loopback lab, not a hosted multi-tenant product. It has no user authentication, remote access controls, external backups or high availability. Kubernetes RBAC limits the dev credential to patching one named Service, but RBAC cannot limit patch fields; the application enforces selector-only patches. Keep the restricted token private and do not expose Streamlit or the history API publicly.

The next capstone increments are independent human review of the recorded investigations and judge disputes, and a few new held-out history cases. Richer provenance, logs/metrics and additional repairs are intentionally deferred. Do not expand to the financial project.

## Verification for this milestone

The live exercise created a selector mismatch in `dev-capstone/demo-web`, recorded its change, investigated it with the real model and RAG, restored the selector through the restricted dev identity, and observed ready endpoints return. A collector restart preserved the same Service-history IDs without duplicates. Kubernetes authorization checks denied production patches, Secret reads and Pod deletion. Both capstone nodes and the collector were healthy at verification.

235 local tests passed, including scope isolation, persistence/deduplication, timestamp normalization, missing-history limits, invalid tools/citations, conditional repairs and rollback. Ruff and Bandit checks passed. See [machine-readable verification](cluster-history-verification.json).

Manual review caught an earlier model answer that blamed initial Pod readiness for a later selector outage. The revised endpoint investigation requires Service history, current Pod labels, current EndpointSlices and a runbook before it can finish. The final live answer identified the selector mismatch and limited its recovery claim to endpoint discovery/readiness, recommending a separate connectivity check. This correction is a development result, not proof of general diagnostic accuracy. The new history path still needs a held-out evaluation set.

Timeline queries are bounded: the UI shows the latest 100 records; the agent receives at most six matching history records per tool call and can narrow by resource kind/name. Truncation is reported. This milestone does not exhaustively scan every record in a busy month.

## November 22 workflow verification

The dedicated cluster was restarted after being stopped; both nodes and the collector are Ready. The interruption remains part of coverage and is not backfilled. The main UI serves live history and three offline snapshot demos. Six final paired model investigations completed; 259 offline tests, lint and static security checks passed. A read-only live smoke check performed Service history, current Service, Pod and EndpointSlice reads and a runbook query. It is an integration check, not an accuracy verdict: the model still overinterpreted some gap evidence. No dev repair or production mutation was executed in this milestone.
