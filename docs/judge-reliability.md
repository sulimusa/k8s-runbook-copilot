# Judge reliability: corrections and remaining review

## Final correction pass — November 22

All **31 queued model findings** from the older 24-case study now have explicit [developer review decisions](judge-adjudications.json): 22 rejected deductions, two accepted defects and seven wording corrections. These decisions preserve the full quoted context and bind to answer/context hashes. The four earlier known regression adjudications are also retained. Original answers and numeric ratings were not rewritten or converted into a new accuracy score.

The updated judge passed **nine constructed controls**, including Service selection, conditional advice, absent logs, repeated termination claims and potential-versus-measured memory. It still produced **four false deductions on the final six demo answers**. Passing controls did not generalize perfectly; the final [demo adjudications](history-demo-adjudications.json) explain each disagreement against the complete answer and evidence.

Solver corrections distinguish Service discovery from endpoints, restart count from last termination reason, and potential cache budgets from actual consumption. Narrow evidence guards request a corrected model answer; they do not silently edit its text. Guard retries and failed attempts remain in the reports. They are targeted checks, not a comprehensive factual validator.

For Kubernetes semantics, the review used the official [EndpointSlice documentation](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/) and [resource-management documentation](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/). Unready endpoints can exist; memory enforcement does not make a configured budget equivalent to observed allocation.

Reviewer identity remains **implementation assistant**, not an independent human domain reviewer. The final comparison supports a narrow claim about more specific investigation checks, not a factual-accuracy leaderboard.

## Earlier November 22 update

We preserved every frozen solver answer and every earlier rating. The new evaluation process separates **usefulness against a reference** from **factual claims against the context actually supplied**. A factual reviewer never receives the reference answer or another candidate's response.

The known issues now have explicit developer adjudications and regression protection:

| Known defect | Treatment |
|---|---|
| Conditional restart treated as unconditional | Preserve the complete preceding condition; reject the known deduction. |
| Aggregate DB budget treated as a known per-replica pool | Reject the known missing-context deduction; a requested check is not an assertion. |
| Configured cache ceiling treated as actual cause | Accept the overclaim defect; calculations are not measurements. |
| Unavailable reload logs treated as an observed missing event | Accept the presupposition defect; request the logs rather than assert their contents. |

See [the review queue and explicit adjudications](judge-review-queue.json). Adjudications were made by the implementation assistant, **not an independent human domain reviewer**. Their exact answer substrings are checked so edited answers cannot inherit stale adjudications.

## What was run

- Five constructed negative/positive controls passed a separate OpenAI judge: conditional restart, aggregate connection cap, unavailable logs, potential memory budget, and fabricated production recovery.
- All 24 original three-arm answer sets received a further claim-aware review. It caught the memory overclaim, but still mishandled some conditions. These [raw ratings](knowledge-value-live-claim-reviewed-results.json) are explicitly marked disputed; their factual averages are not accepted performance results.
- All 72 original answers then received a context-only factual review. This removed reference leakage, but did not eliminate semantic errors: the model still sometimes flags hypotheses or clips a prerequisite from a quote.
- The review gate now attaches the complete enclosing context, rejects unmatched quotes, and queues ambiguous deductions. It **does not silently convert a model complaint into a factual score or publish an all-pass verdict**.
- The six new historical demo answers were independently reviewed too. Raw findings are retained in [history demo review](history-demo-review.json); they include disputed judgments about explicitly qualified hypotheses and standard selector semantics. Passing schema checks is not passing semantic evaluation.

## Reproduction

From the repository root, with the configured bounded model and remaining shared budget:

```sh
# These create new files; keep previous runs for comparison.
python -m eval.knowledge_value.review_v3 calibrate eval/reports/new-calibration.json
python -m eval.knowledge_value.review_v3 review eval/reports/knowledge-value-development-v3 --calibration eval/reports/new-calibration.json
python -m eval.knowledge_value.factual_review eval/reports/knowledge-value-development-v3
```

Review directories are versioned and refuse incompatible protocols; do not overwrite old experiments to make a score look better. The frozen study code, observations, prompts and reference keys were not changed.

The independent human task remains: review a mixed sample of correct claims, conditional advice, genuine overclaims and safe abstentions; compare decisions with the queued judge issues. The project demonstrates evaluation debugging, not a perfectly reliable LLM judge.
