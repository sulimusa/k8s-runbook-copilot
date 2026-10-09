"""Deterministic guardrails that do NOT depend on the LLM obeying its prompt.

1. Command allowlist  - only read-only `kubectl` invocations may appear in `diagnostic_commands`.
2. Remediation flags  - write actions may appear as *guidance* only, clearly marked as manual.
3. Citation check     - every citation must be a chunk that was actually retrieved.
4. Groundedness       - evidence strings must be lexically supported by the retrieved text.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from .retrieval.text import tokenize

# verb -> allowed sub-verbs (None = any). Everything else is rejected.
READ_ONLY_VERBS: dict[str, set[str] | None] = {
    "get": None, "describe": None, "logs": None, "top": None, "events": None,
    "explain": None, "api-resources": None, "api-versions": None, "version": None,
    "cluster-info": None,
    "rollout": {"status", "history"},
    "auth": {"can-i"},
}
SAFE_PIPE_TARGETS = {"grep", "head", "tail", "wc", "sort", "uniq", "cut"}
# Flags that are never acceptable even on read verbs.
BLOCKED_FLAGS = ("--as", "--as-group", "--token", "--kubeconfig", "--raw", "--insecure-skip-tls-verify")
_PLACEHOLDER = re.compile(r"<[A-Za-z0-9_.-]+>")
_FORBIDDEN_CHARS = re.compile(r"[;&`><\n\r]|\$\(|\|\|")

# Write verbs: allowed in remediation text only when flagged as manual.
WRITE_VERBS = ("delete", "apply", "patch", "scale", "edit", "replace", "drain", "cordon", "uncordon", "taint",
               "label", "annotate", "set ", "create", "run ", "exec", "debug", "cp ", "rollout undo",
               "rollout restart", "rollout pause", "rollout resume", "autoscale", "expose", "certificate approve")
# Never allowed anywhere in the output.
HARD_BLOCK = (r"--force\b", r"--grace-period[= ]0", r"delete\s+(ns|namespace|nodes?|pv|pvc)\b", r"--all\b.*delete|delete.*--all\b",
              r"rm\s+-rf", r"kubectl\s+delete\s+.*--all", r"\bsudo\b", r"curl[^\n]*\|\s*(ba)?sh", r"kubectl\s+get\s+secrets?\b.*-o")
MANUAL_PREFIX = "[Manual change - review and test first] "


@dataclass
class CommandCheck:
    ok: bool
    reason: str = ""


def check_command(cmd: str) -> CommandCheck:
    c = cmd.strip()
    if not c:
        return CommandCheck(False, "empty")
    c = _PLACEHOLDER.sub("PLACEHOLDER", c)
    if _FORBIDDEN_CHARS.search(c):
        return CommandCheck(False, "shell metacharacter / redirection / chaining")
    segments = [seg.strip() for seg in c.split("|")]
    for seg in segments[1:]:
        try:
            first = shlex.split(seg)[0]
        except (ValueError, IndexError):
            return CommandCheck(False, "unparseable pipe target")
        if first not in SAFE_PIPE_TARGETS:
            return CommandCheck(False, f"pipe target '{first}' not allowed")
    try:
        toks = shlex.split(segments[0])
    except ValueError:
        return CommandCheck(False, "unparseable")
    if not toks or toks[0] != "kubectl":
        return CommandCheck(False, "only kubectl commands are allowed")
    rest = toks[1:]
    # skip global flags before the verb (e.g. -n ns, --context x)
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        i += 2 if rest[i] in ("-n", "--namespace", "--context", "-l", "-c") else 1
    if i >= len(rest):
        return CommandCheck(False, "no verb")
    verb, args = rest[i], rest[i + 1:]
    if verb not in READ_ONLY_VERBS:
        return CommandCheck(False, f"verb '{verb}' is not read-only")
    allowed_sub = READ_ONLY_VERBS[verb]
    if allowed_sub is not None:
        sub = next((a for a in args if not a.startswith("-")), None)
        if sub not in allowed_sub:
            return CommandCheck(False, f"'{verb} {sub}' is not read-only")
    for t in rest:
        if any(t == f or t.startswith(f + "=") for f in BLOCKED_FLAGS):
            return CommandCheck(False, f"flag {t} not allowed")
    if verb == "get" and re.search(r"\bsecrets?\b", " ".join(args)) and any(a.startswith(("-o", "--output")) for a in args):
        return CommandCheck(False, "reading secret contents is not allowed")
    return CommandCheck(True)


def filter_commands(cmds: list[str]) -> tuple[list[str], list[str]]:
    kept, dropped, seen = [], [], set()
    for c in cmds:
        c = c.strip().strip("`")
        if check_command(c).ok:
            if c not in seen:
                kept.append(c)
                seen.add(c)
        else:
            dropped.append(c)
    return kept, dropped


def sanitize_remediation(items: list[str]) -> tuple[list[str], int]:
    """Drop hard-blocked advice; prefix any write action with a manual-review marker."""
    out, flagged = [], 0
    for it in items:
        low = it.lower()
        if any(re.search(p, low) for p in HARD_BLOCK):
            flagged += 1
            continue
        if "kubectl" in low and any(v in low for v in WRITE_VERBS) and not it.startswith(MANUAL_PREFIX):
            it = MANUAL_PREFIX + it
            flagged += 1
        out.append(it)
    return out, flagged


def check_citations(citations: list[str], retrieved_ids: set[str]) -> tuple[list[str], list[str]]:
    kept = [c for c in dict.fromkeys(citations) if c in retrieved_ids]
    dropped = [c for c in citations if c not in retrieved_ids]
    return kept, dropped


def groundedness(evidence: list[str], context_texts: list[str], threshold: float = 0.6) -> float:
    """Fraction of evidence items whose content words are mostly present in the cited context.
    Lexical, deliberately simple and deterministic (an LLM judge is a documented upgrade)."""
    if not evidence:
        return 1.0
    ctx = set()
    for t in context_texts:
        ctx.update(tokenize(t))
    ok = 0
    for ev in evidence:
        toks = set(tokenize(ev))
        if not toks:
            continue
        if len(toks & ctx) / len(toks) >= threshold:
            ok += 1
    return ok / len(evidence)
