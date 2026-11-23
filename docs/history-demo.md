# Historical investigation: three capstone demonstrations

The main question is: **What changed before this failure, and does operational knowledge improve the investigation?**

Run `make history-chat` and open <http://127.0.0.1:8501>. Select **Three capstone demos** in the sidebar. Expand **Recorded model comparison — no API call** to read the same scenario with history tools alone and with operational retrieval. Each column includes the actual tool trace and citations. Selecting a case does not spend API credits. **Investigate this demo with the model** starts a new paid run using the shared cap.

The snapshots are fictional and fixed at November 20, 2026. They use the same `investigate` function and read interface as live cluster chat, with an injected read-only snapshot client and clock. There is no Kubernetes connection or repair button in demo mode. They do not demonstrate a live fault injection, real customer impact, or a month of actual collection.

## 1. Rollout and OOM: knowledge can improve next checks

Question: Why did cache-api restart after a rollout, and what should we check before mitigation?

History shows a v1 → v2 image change, unchanged 512 MiB limit, and a subsequently observed Pod with OOMKilled termination. The applicable fictional v2 contract describes defaults of four workers with a maximum 192 MiB cache each. The potential budget is 768 MiB before other allocations. Runtime overrides and actual allocations remain unknown.

Compare the answers: history alone suggests investigating memory use, workload and compatibility. Retrieval adds specific checks for effective worker count and cache budgets. **Neither answer may treat a configured maximum as measured usage or a proven root cause.** Old-version and wrong-environment contracts are excluded by explicit fixture metadata, not answer keys.

The current export is `history-demo-v9`: five successful v8 answers retained unchanged, with only the failed OOM/RAG arm retried after a validation bug was fixed. Both OOM answers now separate the three restarts from the last reported OOM termination. Neither infers failed Service DNS discovery from Pod unreadiness or absent slices. RAG supplies the 768 MiB potential budget and effective-setting checks; both still need runtime evidence. "Most likely" in the model output is qualitative, not calibrated cause confidence.

The answers were not manually rewritten. The first guard was too broad and rejected a valid statement containing "repeated restarts; only the last termination was OOMKilled". The corrected guard has a regression test for that distinction. Failed runs remain preserved; this is development debugging, not a clean held-out benchmark.

## 2. Selector change: evidence is sufficient without RAG

Question: Why does demo-web have no endpoints, and is customer impact known?

The retained Service change replaces `app=demo-web` with `app=no-matching-pods`. Current Pods still have the former label; the EndpointSlice is empty. Both arms inspect Service history, Pod labels and EndpointSlices before finishing. Both identify the selector mismatch.

Generic operational guidance may repeat verification advice, but the mechanism is already supported by cluster evidence. This is a deliberate control: **more retrieved text is not automatically a better diagnosis**. Discovery readiness is distinct from network, HTTP and business recovery.

## 3. Earlier outage: retrieval cannot recover missing history

Question: What deployment caused the November 5 outage, and is rollback justified?

Collection starts November 18. A baseline shows the first observed payments-api state; it is not a deployment date. Both arms must disclose the gap, decline causal attribution, and request retained incident-time records. The final recorded answers classify this as insufficient evidence.

## Reviewer walkthrough (about five minutes)

1. Select the OOM case and expand the saved comparison. Identify the extra configuration detail in RAG, then the remaining uncertainty in both columns.
2. Select the selector case. Verify that both columns identify the same mechanism; inspect the actual history/current tool reads.
3. Select the earlier-outage case. Confirm the coverage boundary, baseline label and refusal to justify rollback.
4. Return to **Live cluster history** for the collector-backed interface when the dedicated lab is running. Production is read-only; dev restoration is a separate explicit control.

## Reproduce and evaluate

From the repo root with the environment activated:

```sh
make history-demo-test
# New model runs: explicit configured credentials/prices/shared budget required.
make history-compare RUN_DIR=eval/reports/history-demo-new
python -m eval.history_demo_review eval/reports/history-demo-new
```

The 3-case corpus and fictional contracts are under `data/history_demo/`; evaluator expectations are separately stored in `eval/history_demo_keys.json`. The solver never loads that file. A larger downloaded public corpus is not needed to reproduce this focused demonstration. The live chat still uses the broader public corpus. General live service/version-scoped document ingestion is not implemented by this demo.

Saved results: [six actual model investigations](history-demo-results.json). Earlier attempts remain in ignored local `eval/reports/history-demo-v1` through `v8`; they are not silently replaced. Initial attempts exposed summary-only citations and overconfident causal wording. The final schema separates observations, explanation, alternatives, missing evidence, mitigation conditions and verification. Timeline IDs/timestamps are checked against full retrieved records; citation errors trigger bounded corrective retries. This checks provenance, not the truth of every generated sentence.

These are development demonstrations, not held-out evaluation. One model generation per final arm/case does not establish statistical superiority. The prior [24-case study](knowledge-value-results.md) is a separate experiment with different frozen inputs and its own limitations.

## Judge review and what the comparison supports

The revised judge passed nine constructed controls, but still made four false deductions on these six answers. [Full-context developer adjudications](history-demo-adjudications.json) record the exact quotes, answer hashes and decisions; [raw findings](history-demo-review.json) remain unchanged. The implementation assistant reviewed all six full answers against their evidence and found no remaining blocking factual error in the current recorded outputs. This is not independent human validation or a guarantee about new generations.

| Case | Observed contribution | What is not established |
|---|---|---|
| Rollout/OOM | RAG adds four-worker/per-worker cache semantics and targeted effective-setting/allocation checks. | That the cache actually consumed 768 MiB, caused every restart, or was the true root cause. |
| Selector mismatch | Both arms identify the same evidence-supported exclusion of the observed Pod. | Any necessary diagnostic improvement from generic retrieved guidance. |
| Missing history | Both arms withhold attribution and rollback justification. | An ability for RAG to recreate missing incident-time records. |

This demonstrates **where retrieval changes useful next checks**, not that RAG generally beats an LLM with the same evidence. Both arms use the same model, initial snapshots, prompt and tool bounds; adaptive read choices can differ. All three cases have been used during development. The next evaluation step is independent human labels and new held-out cases, rather than more reruns until a judge agrees.

The UI includes the actual answers, tool traces, a concise comparison note, and expandable judge decisions. Browsing them incurs no API charge.
