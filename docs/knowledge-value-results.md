# RAG comparison results — November 6, 2026

**November 22 follow-up:** [judge reliability corrections](judge-reliability.md) preserve these historical results and add context-only factual review, full-clause review gates and explicit adjudication of the four known problems. Raw model ratings remain fallible. The new [history-first demonstration](history-demo.md) is a separate experiment.

**Conclusion: service-specific retrieval made the next step more actionable in this small
synthetic study. It added no rated benefit on generic Kubernetes problems or when the needed
contract was missing. We do not claim a demonstrated improvement in factual accuracy.**

We ran 24 cases in three modes, producing 72 real model answers. The primary comparison is
**the same observations without retrieval versus the same observations with retrieval**.
The question-only arm is a secondary context-availability baseline.

Both solver and separate judge calls used the fixed `gpt-4.1-2025-04-14` snapshot. The model,
settings, observations and original prompts were held constant across the frozen development
and reserved-test runs. No answers were regenerated, cherry-picked or replaced.

## What improved, and what did not

These are the **context-aware second-pass judge's usefulness ratings**, on a zero-to-two
ordinal scale. They are not percentages of accuracy. Known judge errors are discussed below.

| Case group | Cases | Evidence-only mean | RAG mean | RAG better / tied / worse |
|---|---:|---:|---:|---:|
| Service knowledge changes the decision | 12 | 1.08 | 2.00 | 11 / 1 / 0 |
| Generic Kubernetes problem | 6 | 2.00 | 2.00 | 0 / 6 / 0 |
| Applicable service contract missing | 6 | 2.00 | 2.00 | 0 / 6 / 0 |

The service-specific benefit appeared in both splits: six of six development cases and five
of six reserved-test cases received a higher usefulness rating. The sixth reserved case,
`replay-a`, tied: the evidence-only answer already asked for the output and deduplication checks.
There were no generation/API/schema failures in the 72 predictions and no missing judge records.

Examples from the saved answers:

| Case | Evidence-only | What retrieval added |
|---|---|---|
| `release-a` | Investigate the error spike and whether migrations occurred before rollback. | Identifies schema epoch 9 as incompatible with the previous release; check the migration record and use a forward-compatible fix if it ran. |
| `memory-b` | Obtain a profile to identify the cache's contribution. | Confirms the 192 MiB cache is shared, so multiplying by four workers would be wrong. Actual allocation evidence is still needed. |
| `shutdown-b` | Establish job duration and drain behavior before increasing the timeout. | The documented drain should finish within 15 seconds; a kill at 30 seconds points toward blocked shutdown/dependencies rather than normal long jobs. |
| `scaling-a` | Verify connection usage and capacity before scaling. | Calculates that twenty replicas could demand 400 connections against a 240-connection budget. |
| `release-control` | Identifies the Service selector mismatch from observed labels and empty endpoints. | No material improvement; the observations were already sufficient. |

This is the value of *providing the right knowledge*, not evidence that the underlying model
became smarter. Manually supplying the same relevant contract might work equally well; this
study has no all-documents/manual-context arm. Our engineering contribution is selecting and
maintaining that context automatically, with scope, provenance and coverage checks.

## The judge was part of the debugging work

We preserved the original 24 ratings. Their rationales sometimes penalized non-RAG answers for
not citing or calculating facts from documents they never received. That conflated **reference
completeness** with **correctness and grounding**, exaggerating RAG's apparent advantage.

We then:

1. Clarified the judge's dimension boundaries using development-set failures.
2. Added a three-candidate control: cautious evidence-only, fabricated execution/causality,
   and a qualified contract-grounded recommendation.
3. Preserved the first failed calibration: it gave fabricated production execution a partial
   safety score. Clarified that unverified claims of executed actions are a safety failure.
4. Passed the same explicit calibration criteria with the revised wording.
5. Re-reviewed **all 24 original answer sets**, including controls, with the revised judge.

No generator prompts, retrieval results, reference keys or model answers changed between
reviews. The improvement was to the evaluation procedure; it was not tuning until RAG won.
The reviewer remains the same provider/model in a separate context, not independent ground truth.

### Remaining judge and answer problems

Assistant inspection still found issues after calibration; an independent human has not
reviewed the keys or these annotations. We did not silently overwrite the ratings.

- **`certificate-a`, evidence-only:** the answer says to check reload support and restart **if
  not supported**. The judge treated it as an unconditional/premature restart recommendation.
  Its deductions for correctness, grounding and safety are disputed.
- **`scaling-b`, evidence-only:** the 240-connection aggregate cap does not reveal the
  per-replica pool size. The judge incorrectly penalized the answer for treating that size
  as unknown. This is precisely the private fact the baseline did not receive.
- **`memory-a`, RAG:** the configured potential cache budget is 768 MiB, but there is no
  measurement of actual cache allocation. The answer says reducing it would be
  “directly addressing the cause.” That is stronger than the evidence warrants. The judge
  gave full uncertainty/grounding credit despite this wording.
- **`certificate-a`, RAG:** asking why no reload event *is logged* can imply an observed absence,
  whereas the fixture only says no reload log is available. Prefer “obtain the reload logs.”

Therefore, the judge's perfect scores for RAG and its report of zero regressions are **not
proof of error-free or safer answers**. We retain the directional usefulness result, show
concrete examples, and do not use the apparent correctness/grounding score gains as evidence
of a product advantage. A passed toy calibration did not establish general judge reliability.

## Retrieval quality, cost and latency

The earlier development retrieval audit used 682 chunks. Scope filtering reduced cases with
inapplicable service contracts from 11/12 to 0/12 while retaining all six decisive contracts.
That was an offline document-selection comparison; we did **not** run an additional paid
unfiltered-RAG answer arm.

| Generation mode | Input tokens across 24 cases | Median provider-call latency | Tracked generation cost |
|---|---:|---:|---:|
| Question only | 8,994 | 2.33 seconds | $0.062884 |
| Evidence only | 10,803 | 2.33 seconds | $0.068894 |
| Evidence + RAG | 81,947 | 2.68 seconds | $0.221054 |

RAG used about **7.6 times the input tokens** and **3.2 times the generation cost** of
evidence-only. The latency figure covers the model call, not a deployed end-to-end request.
These observations favor selective retrieval and concise context, rather than attaching a
large document bundle to every generic problem.

| Spending | Tracked USD |
|---|---:|
| Earlier capstone calls | 0.93574075 |
| 72 predictions | 0.352832 |
| Original 24 judge reviews | 0.353084 |
| Two calibration calls | 0.054608 |
| Revised 24 judge reviews | 0.369404 |
| **This comparison, including evaluation debugging** | **1.129928** |
| **Cumulative total against the approved $6 cap** | **2.06566875** |

No unknown-cost reservations remain. Accounting conservatively uses standard non-cached
rates; the eventual invoice may be lower due to caching. The configured $2 input / $8 output
per million token rates were checked against the [official model page](https://developers.openai.com/api/docs/models/gpt-4.1).
The ledger was backed up and its cap explicitly raised; earlier spend was not reset.

## What this means for the capstone

Keep RAG for service-specific behavior, safe-change constraints and historical operational
knowledge. Keep direct observation tools for facts about the cluster. Generic failures may
need those observations without additional service documents. When the applicable knowledge
is missing, retrieve or request it rather than substitute another version's guidance.

The next product improvement should enforce the distinction between **documented potential**
and **observed behavior**, and preserve conditional language in recommendations. Those are
findings from this comparison, not claims that the fixes are already implemented.

This is one run per arm, on fictional services in an author-aware family-disjoint split.
The reserved set is not independently authored or sealed. The study does not establish
performance on real incident logs, adaptive live tool selection, month-long history, a newer
model, or another agent equipped with the same tools and knowledge. It does provide a
reproducible capstone example of building, measuring, finding evaluation defects, and
reporting limitations honestly.

## Review the evidence

- [Protocol and reproducible commands](knowledge-value-evaluation.md)
- [All 72 answers and original judge ratings](knowledge-value-live-results.json)
- [The same answers and context-aware ratings](knowledge-value-live-context-reviewed-results.json)
- [Review annotations, calibration outcomes and spend verification](knowledge-value-review-audit.json)
- [Original offline retrieval audit](knowledge-value-retrieval-results.json)

The local frozen folders remain `eval/reports/knowledge-value-development-v3` and
`eval/reports/knowledge-value-reserved-test-v3`. First-pass records live in `judgments/`;
second-pass records live in `judgments-context-aware-v2/`. Both sets are retained.
