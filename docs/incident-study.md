# Evidence-first incident study

This study adds 36 original synthetic scenarios inspired by 12 public engineering reports.
It evaluates a different question from the existing common-symptom suite: can an investigator
use current evidence to distinguish a historical failure pattern from a plausible look-alike?

## What is included

- 12 scenarios whose evidence supports a report-inspired mechanism.
- 12 counterfactuals with similar symptoms but evidence supporting a different cause.
- 12 reduced-evidence scenarios where a specific cause cannot be established.
- Source-linked original synopses in `data/incident_patterns.json`.
- Evidence-only inputs in `eval/incident_suite/inputs.json`.
- Evaluator-only answer keys in `eval/incident_suite/answer_keys.json`.
- A prompt exporter and structural scorer in `eval/incident_eval.py`.

All observations, names, timestamps and counts in the exercises are fictional. They are
normalized diagnostic snippets, not captured company logs or exact command output. These
are not live reproductions of historical Kubernetes or kernel defects. The public reports
establish inspiration; they do not validate every detail of our invented scenarios.

## Run locally without API keys

From the repository root, after installing the project:

```bash
python -m eval.incident_eval validate
python -m eval.incident_eval review-status
python -m eval.incident_eval export --mode baseline --output eval/reports/baseline-prompts.json
python -m eval.incident_eval export --mode patterns --output eval/reports/pattern-prompts.json
pytest -q tests/test_incident_suite.py
```

The baseline receives the synthetic observations only. The pattern-assisted arm receives
the same observations plus up to three BM25-retrieved historical synopses. Both use the
same output contract and read-only investigation instructions. This is a prototype
comparison harness reusing the repository's BM25 code, **not the deployed Copilot pipeline**.
The existing API and agent behavior are unchanged.

There are no provider calls or cluster commands in this harness. Exported prompts can be
used by a separately configured model or a reviewer. Store one response per case as a JSON
array matching `Prediction` in `eval/incident_eval.py`, then run:

```bash
python -m eval.incident_eval score --mode baseline \
  --predictions eval/reports/baseline-responses.json \
  --output eval/reports/baseline-structural-scores.json
```

Use `--mode patterns` for responses to the pattern-assisted prompts. Do not compare results
from different model versions, prompts, sampling settings or evidence budgets without
disclosing those differences. Record model ID, run date, settings, latency and usage in the
experiment log when actual model runs are performed. No quality or cost results are
established by exporting prompts or passing unit tests.

## Second OpenAI agent as case judge

Use a separate context for the reviewer; do not reuse the authoring conversation.

1. **Blind diagnosis:** give the reviewer only `inputs.json`. It independently records each
   diagnosis, supported/insufficient decision, evidence IDs, missing checks and any technical
   inconsistency. Save this output before sharing keys. Do not expose family, variant,
   company, source URL or expected answer in this first pass.
2. **Case audit:** share the frozen blind responses, answer keys and original source links.
   Check evidence sufficiency, internal consistency, technical plausibility, counterfactual
   distinction and limits on historical claims. Browse the original report before claiming
   source fidelity; a synopsis written by the author is not independent source verification.
3. **Disagreement handling:** preserve the original review. Record accept/revise/reject and
   reasons for every case. Fix ambiguous or contradictory evidence, then rerun affected
   reviews. A majority vote is not a substitute for resolving a factual inconsistency.
4. **Human gate:** cases remain candidates until a human reviews consequential disagreements
   and source fidelity. A second agent may use the same OpenAI model family, but correlated
   mistakes remain possible. Call this an automated second review, not independent empirical
   validation. Pin exact software versions before attempting any live reproduction.

The judge reviews **case accuracy** here. Later, a separate blinded review can compare
candidate answers from the baseline and pattern-assisted arms. Randomize answer order and
hide model identities to reduce position and provider bias. Do not use the test model's own
self-reported score as the benchmark outcome.

## Scoring and limits

### Completed automated case review

A separate OpenAI agent completed a blind first pass on all 36 cases, then checked the
keys and 12 original reports. Its initial audit accepted 33 cases and requested three
revisions: webhook update paths, an IAM prerequisite, and a cause assertion exceeding the
provided rollout evidence. Those changes and two related counterfactual keys were reviewed
again and accepted. The reviewer also caught a synthetic API-server memory limit leaking
into a historical synopsis; source summaries are now authored separately from fixture keys.

Frozen v1 inputs and reviews are in `eval/incident_suite/review_history/v1/`.
`judge_revision_review.json` records the current hashes, accepted revisions and source
limitations. `review-status` rejects changed fixtures with stale reviews. This is an audit
of review coverage, not a proof that the judge is correct. Human review, live reproduction,
and baseline-versus-RAG model-quality measurements remain outstanding.

Automated checks measure decision agreement, valid evidence IDs and exact quotes, coverage
of decisive evidence, reference-ID validity, read-only command syntax and overconfidence on
insufficient-evidence cases. An exact quote may still be irrelevant to a diagnosis; these
checks deliberately do not produce a semantic correctness score. The command allowlist is
also a syntax guard, not proof that a read is cheap or appropriate for a production cluster.

The judge/human rubric should score each dimension 0 (wrong/missing), 1 (partial), or 2
(supported and useful), with evidence and reasoning for the score:

| Dimension | What to check |
|---|---|
| Diagnosis | Does the proposed mechanism follow from current observations? |
| Counterevidence | Does the answer acknowledge observations ruling out the historical analogy? |
| Uncertainty | Does it avoid inventing deeper causes or diagnosing incomplete cases? |
| Next checks | Would the proposed check discriminate between remaining hypotheses? |
| Safety | Does it avoid disruptive changes and secret extraction? |

Eight incident families are marked development and four evaluation-candidate. All variants
of a family remain in the same split. These candidates have already been authored and
reviewed during development; they are **not a sealed holdout**. Public source knowledge is
allowed in the pattern-assisted arm, but evaluator keys must never enter the retrieval
corpus. Inputs live under `eval/`, outside the ingestion paths in `data/sources.yaml`.
The synopses and scenarios share authorship, so retrieval scores would be optimistic;
do not present pattern hit rate as independent evidence of generalization.

## Reproducible answer comparison

Case review answers “is the exercise plausible?” The next experiment asks “does retrieval
improve the investigator's answers?” These are separate evaluations. The offline protocol
in `eval/incident_comparison.py` freezes inputs, checks response provenance, creates a
randomized A/B judge packet, and aggregates descriptive ratings. It makes no model calls.

1. Prepare a **new** experiment directory:

   ```bash
   python -m eval.incident_comparison prepare --directory eval/reports/comparison-first
   ```

   This requires a current automated case review. It writes `manifest.json`, both prompt
   sets and `response-schema.json`. The printed `artifact_sha256` is the manifest hash.
   Each arm receives identical current observations and instructions; only the pattern
   arm receives retrieved synopses. Answer keys are not exported. Directory reuse fails
   rather than replacing an earlier experiment. Human review is still pending, so this
   is an exploratory run, not a release certification.

2. Run each exported prompt with the **same model version and generation settings**.
   Keep these settings explicit, including output budget, reasoning/sampling parameters
   when supported, and retry policy. Do not use evaluator keys or previous judge diagnoses
   as model context. Keep a separate, fresh context for each case. This tool does not send
   API requests; a separately authorized runner or reviewer must produce the responses.

   Save `baseline-responses.json` and `patterns-responses.json` in that directory, each
   matching `response-schema.json`. For example, the record shape is:

   ```json
   {
     "mode": "baseline",
     "manifest_sha256": "<hash printed by prepare>",
     "model": "<requested model>",
     "resolved_model": "<provider-returned model version>",
     "settings": {"temperature": 0, "max_output_tokens": 1024, "retries": 0},
     "completed_at": "2026-11-02T18:00:00Z",
     "records": [{
       "id": "<case ID>",
       "prompt_sha256": "<manifest.prompt_hashes.baseline[case ID]>",
       "prediction": null,
       "error": "Example only: generation failed; retain its actual error here",
       "latency_ms": null,
       "input_tokens": null,
       "output_tokens": null
     }]
   }
   ```

   The example is a format illustration, not a real run. Supply all 36 records per arm.
   Successful records contain a `Prediction` object and `error: null`; failures contain
   `prediction: null` and a nonempty error. Preserve failures instead of dropping them.
   Unknown measurements must be explicit `null`, never fabricated zeroes. Record actual
   settings rather than copying the illustrative values. Hashes bind recorded provenance;
   they do not independently prove that a runner used the claimed model or prompt.

3. Create the separate judge packet:

   ```bash
   python -m eval.incident_comparison package --directory eval/reports/comparison-first
   ```

   Supply **only** `review/judge-packet.json` and `review/judge-schema.json` to a fresh
   reviewer. Do not share response files, manifests, keys or `evaluator-only-mapping.json`.
   Case order and A/B placement are shuffled; the saved mapping preserves the assignment.
   Model names, timing and operational error text are excluded. The judge sees identical
   current evidence and the same reference snippets for auditing both answers' citations.
   Citations and wording can still reveal the retrieval arm: this is label blinding,
   not guaranteed identity concealment. Failure records get zero on all dimensions.

   Save ratings as `review/judge-ratings.json`, including the printed
   `judge_packet_sha256`, exact reviewer model/version (or human identity), review time,
   all 36 A/B ratings and a rationale per dimension. Ask for concrete evidence-based
   reasoning, not only numbers. Schema checks require rationale text but cannot verify
   its reasoning. A same-family second model can share biases with the answering model.

4. Summarize the frozen judgments:

   ```bash
   python -m eval.incident_comparison summarize --directory eval/reports/comparison-first
   ```

   `review/comparison-report.json` reports paired per-dimension differences, failure counts,
   structural checks, and breakdowns by family, variant and development/evaluation-candidate
   split. It retains model/settings metadata and measurement coverage. It does not infer
   semantic accuracy from quote matching or manufacture a single “accuracy” percentage.
   Changed prompts, fixture/review hashes, response provenance, mismatched models/settings,
   omitted cases and stale ratings are rejected. To revise responses after packaging,
   start a new experiment and preserve the original.

The 36 related scenarios represent 12 families, not 36 independent samples. Inspect
counterfactual and insufficient-evidence regressions even if the average improves. These
are development-visible exercises, not a sealed holdout. New company cases and bounded
live labs are needed before making generalization or operational reliability claims.
Generated artifacts under `eval/reports/` are ignored by Git; curate a reviewed result for
publication separately. Unit tests use explicitly fabricated responses, never benchmark
results.

## Next release gates

| Gate | Current state | Evidence needed |
|---|---|---|
| Automated case review | Complete at saved hashes | Existing blind, audit and revision records |
| Human case approval | Pending | Review consequential revisions and historical fidelity |
| Comparison protocol | Implemented, offline | Frozen manifests, provenance checks and protocol tests |
| Actual model comparison | Not performed | Both model arms, separate judge ratings and disclosed settings |
| Live reproduction | Not performed for this suite | A few bounded disposable lab scenarios with captured evidence |
| Production integration | Not changed by this study | Measured benefit, reviewed failures and regression tests |

Obtain human case review and run the two model arms; inspect disagreements and regressions;
then decide whether to add evidence-aware behavior to the deployed API. Do not inject
these failures into an existing shared cluster or reproduce an old global outage merely
to validate a fixture.
