# Safety model

**Principle: nothing the model writes is ever executed as written.** The triage API has no Kubernetes client, no shell and no
credentials: it returns text, and everything below limits what that text may suggest. **Agent mode** can change a *dev*
environment, but only through typed, bounded actions chosen from a closed list, behind a per-environment policy and an
RBAC-scoped identity, with verification and rollback. Prod is advise-only. Its threat model is in [agent-mode.md](agent-mode.md).

| Threat | Control | Where | Test |
|---|---|---|---|
| Destructive command suggested as a diagnostic | Allowlist: `kubectl` + verbs `get describe logs top events explain api-resources api-versions version cluster-info`, `rollout status/history`, `auth can-i` | `safety.check_command` | `tests/test_safety.py` |
| Command chaining / injection (`;`, `&&`, `\|\|`, `$()`, backticks, redirects) | Rejected; pipes only to `grep head tail wc sort uniq cut` | same | parametrised blocked cases |
| Secret disclosure | `kubectl get secret -o ...` rejected; `--as`, `--token`, `--kubeconfig`, `--raw` rejected | same | yes |
| Write actions in advice | Remediation items containing write verbs are prefixed `[Manual change - review and test first]`; `--force`, `--grace-period=0`, bulk or namespace/node deletes, `rm -rf`, `sudo`, `curl \| sh` are dropped entirely | `sanitize_remediation` | yes |
| `exec` / `debug` / `run` | Not read-only (they create or mutate), so never allowed as diagnostics; the prompt routes them to manual remediation | allowlist + prompt | yes |
| Hallucinated sources | Every citation must be a retrieved chunk id; otherwise dropped, and zero valid citations means abstain | `check_citations` | yes |
| Hallucinated facts | Evidence must be lexically supported by cited chunks; confidence is capped by groundedness; low confidence means abstain | `groundedness`, pipeline | yes |
| Prompt injection in the question | Question and context are delimited as data; system prompt says to ignore embedded instructions; outputs are validated and filtered regardless | prompt + guardrails | eval `ab-05`, `sf-01` |
| Prompt injection in the corpus | Corpus is public, pinned, and reviewed at update time; the same output guardrails apply | pinned SHAs | n/a |
| Sensitive data in logs | Questions are hashed by default (`LOG_QUESTIONS=false`) | `observability.py` | n/a |
| Pasting secrets into the question | Not blocked; **do not paste real secrets or production data into a demo** | README | n/a |

## What the guardrails do not do
- They cannot prove a *diagnosis* is right. They keep every claim traceable to a source so a human can check it.
- Read-only `kubectl logs` can still expose sensitive application output. Treat results as sensitive in real clusters.
- The allowlist is a floor, not a replacement for RBAC: run the commands it recommends with a read-only role.
