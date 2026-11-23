# Does service knowledge improve an investigation?

**Status, November 6, 2026:** the real comparison is complete: 72 predictions, 24 original
judge reviews, two calibration calls and 24 supplementary reviews. [Read the results and
remaining judge defects](knowledge-value-results.md). Cumulative tracked API spend is
$2.06566875 against the user-approved $6 cap. Human review remains pending.


This milestone tests a specific claim: **with the same operational observations,
does retrieving the applicable service contract improve the next investigation step
or recommendation?** A general model can explain Kubernetes. It cannot establish
which private release behavior applies without receiving that information.

## Cases and the people they help

The target user is an on-call engineer deciding what evidence to collect or what
change to propose. There are 24 original fictional cases, organized into six families.
Each family has two contrasting release behaviors, a generic control and a case with
no applicable release contract. No commands execute against a cluster in this study.

| Family | Knowledge changes the decision | Control where service knowledge should add nothing |
|---|---|---|
| Release rollback | An incompatible schema migration makes rollback conditional on the actual migration record; a compatible version supports a guarded rollback proposal. | Service selector does not match Ready Pods. |
| OOM investigation | A cache budget is per worker in one version and shared in another. Multiplying by workers can be correct or misleading. | A new memory limit is below previously observed steady usage. |
| Interrupted jobs | One version needs a 150-second drain allowance; another normally drains in 15 seconds and needs a blocked-shutdown investigation. | A Pod cannot fit its CPU request on any eligible node. |
| Certificate renewal | One version hot-reloads; another requires a controlled restart. | Image registry returns 401 before the container starts. |
| Job replay | Durable idempotency permits a bounded replay after checks; memory-only deduplication requires reconciliation first. | The required image is missing with imagePullPolicy Never. |
| Scaling | Per-replica connection pools make twenty replicas either exceed or fit a database connection budget. | Selector mismatch leaves a Service without endpoints. |

The six missing-contract cases target release r99. Neither an r2 contract, an r3
contract nor a development contract establishes r99 behavior. Asking for the current
contract and missing observations is the expected safe response.

All answer keys are **agent-authored and await human review**. These are synthetic
operating assumptions, not factual claims about real companies. For the memory case,
the fictional setting named CACHE_BUDGET_MB explicitly uses MiB.

## Fair comparison

Every case is evaluated in three arms:

1. **Question only:** question and target scope. A context-availability baseline.
2. **Evidence only:** the same question, scope and frozen observations.
3. **Evidence + RAG:** exactly the same observations, plus retrieved documents.

The primary comparison is **RAG minus evidence-only**. Question-only is not the
main claim of superiority. The solver system prompt, model snapshot, temperature,
output limit and schema are identical across arms. Call order is reproducibly shuffled.
There are no live tools or adaptive evidence collection in this experiment: those
would change another variable and obscure the contribution of retrieval.

The study reuses the project's BM25 retriever. Its current corpus has **682 chunks**:
567 Kubernetes documentation chunks, 91 public runbook chunks and 24 fictional
operating contracts. Only the two public source IDs are admitted from the existing
corpus. Existing Atlas answers, incident answer keys and evaluation files are not
retrieval inputs. The fictional documents live under `data/knowledge_value/`;
case questions and keys live under `eval/knowledge_value/`.

The raw search and scoped search use the same query and ranking implementation.
The scoped version excludes service contracts unless service, environment, release,
active status and effective date match. Public general guidance remains searchable.
Retrieval metrics use answer keys only *after* search to assess the returned IDs.

## Observed retrieval failure and improvement

The development set contains three families, 12 cases and six cases requiring a
specific contract. It deliberately includes archived and wrong-environment distractors.

| Development measurement | Unfiltered search | Scoped search |
|---|---:|---:|
| Required contracts found in top six | 6 / 6 | 6 / 6 |
| Cases returning an inapplicable contract | 11 / 12 | 0 / 12 |
| Inapplicable contracts returned | 34 | 0 |

**What changed:** scope filtering removed unsafe candidate documents without losing
the decisive contracts in this development set. This does not prove the model would
have followed an inappropriate document, nor that filtered answers improve. The completed answer comparison is reported separately, with judge limitations.

The other three families form a reserved 12-case test set. Families do not cross
splits. The protocol and prompts were frozen before paid runs. This is an
**author-aware reserved set**, not a sealed, independently authored blind holdout.
The preparation command creates a retrieval audit for each split, but only development
metrics have been inspected for this report. Do not tune against the reserved cases.

## Judge, failures and evidence of improvement

A separate model call reviews A/B/C candidates with shuffled labels, their available
contexts and evaluator-only reference criteria. Provider identity, arm names, timing
and cost are not in the judge packet. Different contexts remain visible; this is
label blinding, not complete blinding. Using the same provider does not make the judge
independent or authoritative.

Five dimensions are scored from zero to two: correctness, grounding, uncertainty,
safety and usefulness. A justified request for missing facts can score well on
correctness, grounding and uncertainty. Usefulness separately measures whether the
answer makes concrete, supported progress. Unsupported claims are listed explicitly.

The report includes paired RAG-minus-evidence deltas by case type, negative deltas,
failed generations, missing judge reviews, tokens, latency and known/unknown costs.
Generation failures stay in the denominator with zero ratings. Missing or failed
judge reviews make the report incomplete; they are not silently dropped as successes.
These are descriptive results from correlated siblings, not statistical evidence of
production reliability.

Before presenting a model-quality claim:

- Review the fictional contracts and answer keys manually.
- Run development predictions and separate judge reviews within an approved budget.
- Inspect every disagreement, unsupported claim and control-case regression manually.
- Record changes based on those findings, preserving the original run.
- Use a fresh versioned experiment for changes; run the reserved test only after tuning.
- Report both wins and losses, including uncertainty about the judge's ratings.

No automatic remediation is part of the evaluation. Existing dev-fix and production
read-only policy enforcement remains a separate test surface.

## Running the study

From the repository root, activate the documented virtual environment and build the
pinned public corpus with `make ingest` if it does not already exist. Fixture files
are committed source inputs; regeneration is `python eval/knowledge_value/build_fixtures.py`.

Offline preparation and review:

```bash
python -m eval.knowledge_value.study prepare eval/reports/my-development-run
python -m eval.knowledge_value.study audit eval/reports/my-development-run
python -m eval.knowledge_value.study estimate eval/reports/my-development-run
pytest -q tests/test_knowledge_value.py
```

Only after a sufficient API spending limit is explicitly approved and configured:

```bash
python -m eval.knowledge_value.study run eval/reports/my-development-run
python -m eval.knowledge_value.study package eval/reports/my-development-run
python -m eval.knowledge_value.study judge eval/reports/my-development-run
python -m eval.knowledge_value.study report eval/reports/my-development-run
```

`run` and `judge` use the existing local model configuration and shared budget ledger.
They reserve estimated costs before each request, retain unknown-cost reservations,
and never raise or reset the cap. They save each attempted call and resume remaining
calls without rerunning completed files. A failed generation is preserved, not retried
until it looks good. New retries or prompt changes need a new experiment.

`prepare` refuses to overwrite an existing directory. Corpus, cases, keys and prompts
are hashed; code changes invalidate an existing run. Review packets are reconstructed
and checked before judging or reporting. Evidence cannot be silently replaced between
arms, and citations must reference context that the candidate actually received.

A reserved experiment uses `--split reserved_test`. To explicitly compare the older
unfiltered retrieval policy in a new experiment, use `--retrieval unfiltered` at
preparation. That optional extra paid experiment is not included in the current cost
estimate.

The local frozen directories are:

- `eval/reports/knowledge-value-development-v3`
- `eval/reports/knowledge-value-reserved-test-v3`

Generated run folders are ignored by Git. The checked-in
[retrieval results and manifests](knowledge-value-retrieval-results.json) capture the
offline evidence and costs; reviewers can regenerate prompts from source.

## Budget and follow-up

The original conservative estimate was $4.61 additional for the planned 96 calls. The user
approved a $6 cumulative cap on November 6. The completed run, including two calibration calls
and a supplementary full judge review, used $1.129928 of tracked additional cost. The cumulative
ledger total is $2.06566875; no unknown-cost reservations remain. See the results for accounting
assumptions and the preserved first-pass ratings.

The first judge conflated missing private context with factual errors. The revised review
separates completeness from factuality and was calibrated against deliberate false execution
claims. It still has documented errors; do not use its perfect RAG scores as proof of accuracy.
The original frozen solver prompts and all original answers stayed unchanged.

Reproduce the supplementary review after the original workflow using:

```bash
python -m eval.knowledge_value.review_context calibrate eval/reports/my-development-run
python -m eval.knowledge_value.review_context review eval/reports/my-development-run \
  --calibration eval/reports/my-development-run/context-judge-calibration-v2.json
```

The committed exports include every answer and both review passes. `report_live` exports the
fixed local v3 runs; `report_live --context-review` exports the supplementary ratings. Export
commands refuse to overwrite their output files. The prior calibration failure is retained.

Remaining work is independent human review, stronger judge evaluation on conditional statements,
and product handling of documented possibilities versus observed causes. The 36-case broader
incident suite remains separate; this study does not replace it or validate the live chat end to end.
