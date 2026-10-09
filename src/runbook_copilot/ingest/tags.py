"""Cheap keyword tagger: attaches incident-category tags to chunks as metadata (used in reports/filters)."""
import re

CATEGORY_PATTERNS = {
    "CrashLoopBackOff": r"crashloop|back-?off restarting|exit code",
    "ImagePullBackOff": r"imagepull|errimagepull|pull(ing)? (the )?image|imagepullsecret",
    "OOMKilled": r"oomkill|out of memory|exit code 137|memory limit",
    "PodPending": r"\bpending\b|failedscheduling|unschedulable|untolerated taint|didn't match",
    "ProbeFailure": r"liveness|readiness|startup probe|probe failed",
    "DNSServiceConnectivity": r"coredns|kube-dns|nslookup|no endpoints|endpoints?\b.*service|networkpolic",
    "FailedRollout": r"rollout|progressdeadline|replicaset|generation mismatch|replicas mismatch",
    "ResourceQuotaOrNodePressure": r"resourcequota|exceeded quota|diskpressure|memorypressure|pidpressure|eviction",
}
_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in CATEGORY_PATTERNS.items()}


def tag_text(text: str) -> list[str]:
    return [k for k, rx in _COMPILED.items() if rx.search(text)]
