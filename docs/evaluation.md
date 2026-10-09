# Evaluation

40 hand-written cases in `eval/cases/*.yaml`: 34 answerable cases across the 8 incident categories, 1 safety case
(user demands bulk deletion; still answerable, but only read-only), and 5 abstention cases (out of scope,
in-domain but not in the corpus, and a prompt-injection attempt). Retrieval metrics are computed over the 35 answerable cases. Cases were written **before** any retrieval was run; expected sources are substrings of document paths.

## Case schema
```yaml
- id: cl-01
  category: CrashLoopBackOff
  question: "..."
  expected_incident_type: CrashLoopBackOff
  expected_sources: [debug-pods, KubePodCrashLooping]   # any substring match on doc_path counts
  must_include: ["kubectl logs", "a|b"]                 # all required; "a|b" = either
  prohibited: ["kubectl delete pod"]                    # must not appear in any output field
  found_answer: true                                    # false = must abstain
```

## Metrics
| Metric | Definition | Mode |
|---|---|---|
| hit@k, MRR | first retrieved chunk (top k) from an expected source, over answerable cases | retrieval, full |
| gate false-abstention | answerable cases blocked by the retrieval gate | retrieval, full |
| gate catch rate | abstention cases blocked by the gate (rest must be caught by the LLM) | retrieval, full |
| abstention correctness | `found_answer == expected` over all cases | full |
| diagnosis accuracy | `incident_type == expected` over cases the system answered | full |
| must-include pass rate | required facts present in the answer | full |
| citation hit rate | at least one citation from an expected source | full |
| groundedness | share of evidence items lexically supported by cited chunks | full |
| command safety | allowlist + prohibited strings + write actions flagged | full |
| guardrail intervention rate | answers where the model needed a command/citation fix (raw model safety) | full |
| parse success | valid `TriageResponse` within 2 attempts | full |
| latency p50/p95 | end-to-end per request | full |

## Running
```bash
make eval-retrieval                                   # no LLM, instant
python -m eval.run_eval --mode retrieval --exclude-source lab-runbooks   # ablation: public sources only
make eval                                             # needs LLM_API_KEY
python -m eval.run_eval --mode full --ids cl-01 ab-01 sf-01
python -m eval.run_eval --mode retrieval --min-hit5 0.8                   # CI gate
```
Reports land in `eval/reports/` (`latest_<mode>.md` plus timestamped JSON).

## Measured results (retrieval mode, pinned corpus)
| Setup | hit@1 | hit@3 | hit@5 | MRR | gate false-abstain | gate catch |
|---|---|---|---|---|---|---|
| All sources (public + lab runbooks) | 0.914 | 0.971 | 1.000 | 0.939 | 0.0% | 3/5 |
| Public sources only (ablation) | 0.771 | 0.943 | 1.000 | 0.864 | 0.0% | 3/5 |

Full-pipeline numbers are produced by `make eval` with your model; paste them here after your first run.

## Honest caveats
- Dev set, not held-out: the gate thresholds were tuned on these same 40 cases, and the margins are thin (e.g. an
  out-of-scope question scored 20.7 BM25 against a strong-match override threshold of 20). Build a held-out set before quoting accuracy externally.
- The 2 abstention cases the gate does not catch (`ab-01`, `ab-02`) rely on the LLM to abstain; that is what `make eval` measures.
- Lab runbooks were authored for these categories, so the ablation row is the fairer retrieval number.
- Lexical groundedness is a proxy; add an LLM-as-judge or human spot-check before claiming factual accuracy.
