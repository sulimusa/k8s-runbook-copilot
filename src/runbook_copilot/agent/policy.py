"""Per-environment policy: the single place that decides what the agent may do.

The LLM proposes; this module disposes. It is deterministic, has no LLM in the loop, and is the second of three
enforcement layers (1: the Kubernetes identity/RBAC the runner uses, 2: this policy, 3: verification + rollback).

Outcomes
  allow          - apply it (dev / act mode only)
  advise         - the environment is read-only: show the proposal, never execute (prod)
  needs_approval - policy requires a human to approve this action type
  deny           - violates a rule; the reason is recorded in the audit log
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..config import ROOT
from .actions import _container, target_ref
from .quantities import parse_cpu, parse_memory


@dataclass
class Decision:
    outcome: str  # allow | advise | needs_approval | deny
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.outcome == "allow"


@dataclass
class Context:
    """Facts about the cluster the policy needs to validate an action (fetched read-only by the agent)."""

    writes_done: int = 0
    deletes_done: int = 0
    target: dict | None = None  # JSON of the deployment/service/pod being modified
    pod_labels: list[dict] = field(default_factory=list)  # labels of pods in the namespace


def _match(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, p) for p in patterns)


def _image_repo(image: str) -> str:
    base = image.split("@")[0]
    last = base.rsplit("/", 1)[-1]
    return base[: -(len(last) - last.index(":"))] if ":" in last else base


def _image_tag(image: str) -> str:
    last = image.split("@")[0].rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last else "latest"


class Policy:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.environment: str = data["environment"]
        self.mode: str = data["mode"]  # act | advise
        if self.mode not in ("act", "advise"):
            raise ValueError(f"policy mode must be 'act' or 'advise', got {self.mode!r}")
        self.allowed_contexts: list[str] = data.get("allowed_kube_contexts", ["*"])
        self.denied_contexts: list[str] = data.get("denied_kube_contexts", [])
        self.allowed_namespaces: list[str] = data.get("allowed_namespaces", [])
        self.protected_namespaces: list[str] = data.get("protected_namespaces", [])
        self.label_rule: dict | None = data.get("require_namespace_label")
        self.max_steps: int = int(data.get("max_steps", 5))
        self.max_writes: int = int(data.get("max_writes_per_run", 1))
        self.verification: dict = {"timeout_seconds": 120, "poll_seconds": 5, "settle_seconds": 5,
                                   "rollback_on_failure": True, **data.get("verification", {})}
        self.actions: dict[str, dict] = data.get("actions", {})

    @classmethod
    def load(cls, env_or_path: str) -> "Policy":
        p = Path(env_or_path)
        if not p.suffix:
            p = ROOT / "policies" / f"{env_or_path}.yaml"
        return cls(yaml.safe_load(p.read_text()))

    # ----------------------------------------------------------------- environment-level checks
    def check_kube_context(self, kube_context: str | None) -> Decision:
        """Refuse to act through a kubeconfig context that does not look like this environment."""
        ctx = kube_context or ""
        if _match(ctx, self.denied_contexts):
            return Decision("deny", f"kube context '{ctx}' matches a denied pattern for {self.environment}")
        if self.mode == "act" and not _match(ctx, self.allowed_contexts):
            return Decision("deny", f"kube context '{ctx}' is not an allowed {self.environment} context")
        return Decision("allow")

    def check_namespace(self, namespace: str, labels: dict | None) -> Decision:
        if _match(namespace, self.protected_namespaces):
            return Decision("deny", f"namespace '{namespace}' is protected")
        if not _match(namespace, self.allowed_namespaces):
            return Decision("deny", f"namespace '{namespace}' is outside this environment's allowed namespaces")
        if self.mode == "act" and self.label_rule:
            key, want = self.label_rule["key"], str(self.label_rule["value"])
            if (labels or {}).get(key) != want:
                return Decision("deny", f"namespace '{namespace}' is not labelled {key}={want} (opt-in required)")
        return Decision("allow")

    # ----------------------------------------------------------------- action-level checks
    def check_action(self, action: Any, ctx: Context) -> Decision:
        rule = self.actions.get(action.type)
        if not rule or not rule.get("allow"):
            return Decision("deny", f"action '{action.type}' is not permitted in {self.environment}")
        if ctx.writes_done >= self.max_writes:
            return Decision("deny", f"write budget exhausted ({self.max_writes} per run)")
        if _match(action.namespace, self.protected_namespaces):
            return Decision("deny", f"namespace '{action.namespace}' is protected")
        bad = self._bounds(action, rule, ctx)
        if bad:
            return Decision("deny", bad)
        if rule.get("requires_approval"):
            return Decision("needs_approval", f"policy requires human approval for '{action.type}'")
        if self.mode == "advise":
            return Decision("advise", f"{self.environment} is advise-only: proposal recorded, nothing executed")
        return Decision("allow", "within policy")

    def _bounds(self, a: Any, rule: dict, ctx: Context) -> str | None:  # noqa: C901 - one clear branch per action
        kind, _ = target_ref(a)
        needs_target = a.type in ("set_resources", "set_image", "patch_probe", "delete_pod", "patch_service_selector")
        if needs_target and not ctx.target:
            return f"could not read the target {kind} to validate '{a.type}'"
        t = ctx.target or {}

        if a.type == "scale_deployment":
            lo, hi = rule.get("min_replicas", 1), rule.get("max_replicas", 5)
            if not lo <= a.replicas <= hi:
                return f"replicas {a.replicas} outside allowed range [{lo}, {hi}]"

        elif a.type == "set_resources":
            if not (a.memory_limit or a.memory_request or a.cpu_request):
                return "set_resources needs at least one value"
            _, c = _container(t, a.container)
            if c is None:
                return f"container '{a.container}' not found in deployment '{a.name}'"
            cur = c.get("resources") or {}
            cur_limit = parse_memory((cur.get("limits") or {}).get("memory"))
            new_limit = parse_memory(a.memory_limit)
            if new_limit is not None:
                cap = parse_memory(rule.get("max_memory_limit", "1Gi"))
                floor = parse_memory(rule.get("min_memory_limit", "32Mi"))
                if new_limit > cap:
                    return f"memory limit {a.memory_limit} exceeds policy cap {rule.get('max_memory_limit', '1Gi')}"
                if new_limit < floor:
                    return f"memory limit {a.memory_limit} below policy floor {rule.get('min_memory_limit', '32Mi')}"
                mult = rule.get("max_memory_multiplier")
                if mult and cur_limit and new_limit > cur_limit * mult:
                    return f"memory limit may grow at most {mult}x per change (current {cur_limit // 2**20}Mi)"
            eff_limit = new_limit if new_limit is not None else cur_limit
            req = parse_memory(a.memory_request)
            if req is not None and eff_limit is not None and req > eff_limit:
                return "memory request would exceed the memory limit"
            if req is not None and req > parse_memory(rule.get("max_memory_request", "4Gi")):
                return f"memory request {a.memory_request} exceeds policy cap {rule.get('max_memory_request', '4Gi')}"
            cpu = parse_cpu(a.cpu_request)
            if cpu is not None:
                lo, hi = parse_cpu(rule.get("min_cpu_request", "10m")), parse_cpu(rule.get("max_cpu_request", "2"))
                if not lo <= cpu <= hi:
                    return f"cpu request {a.cpu_request} outside [{rule.get('min_cpu_request', '10m')}, {rule.get('max_cpu_request', '2')}]"

        elif a.type == "set_image":
            _, c = _container(t, a.container)
            if c is None:
                return f"container '{a.container}' not found in deployment '{a.name}'"
            cur_img = c.get("image", "")
            if rule.get("same_repository_only", True) and _image_repo(a.image) != _image_repo(cur_img):
                return "image repository must stay the same (only the tag may change)"
            if rule.get("forbid_latest", True) and _image_tag(a.image) == "latest":
                return "the 'latest' tag is not allowed"
            if a.image == cur_img:
                return "image is unchanged"

        elif a.type == "patch_service_selector":
            sel = a.selector
            if rule.get("must_match_existing_pods", True) and not any(
                all(lbls.get(k) == v for k, v in sel.items()) for lbls in ctx.pod_labels
            ):
                return "no existing pod in the namespace matches the proposed selector"

        elif a.type == "patch_probe":
            if a.port is None and a.path is None:
                return "patch_probe needs a port or a path"
            _, c = _container(t, a.container)
            if c is None:
                return f"container '{a.container}' not found in deployment '{a.name}'"
            probe = (c.get(f"{a.probe}Probe") or {})
            if not probe.get("httpGet"):
                return f"existing {a.probe} probe is not an httpGet probe; refusing to merge into it"
            declared = [p.get("containerPort") for p in c.get("ports", [])]
            if a.port is not None and declared and a.port not in declared:
                return f"port {a.port} is not exposed by the container (declared: {declared})"

        elif a.type == "delete_pod":
            if ctx.deletes_done >= rule.get("max_per_run", 1):
                return f"pod-delete budget exhausted ({rule.get('max_per_run', 1)} per run)"
            if not (t.get("metadata") or {}).get("ownerReferences"):
                return "pod has no controller owner; deleting it would not recreate it"
        return None
