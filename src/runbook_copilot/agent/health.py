"""Read-only observation: cluster state, problem detection, and an evidence bundle for the planner.

Every read goes through the same allowlist as the rest of the project (`safety.check_command`), so even this
internal code path cannot issue a write or read secrets."""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field

from ..safety import check_command
from .runner import Runner

BAD_WAITING = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError",
               "CreateContainerError", "InvalidImageName", "RunContainerError"}
_SECRET = re.compile(
    r"(?i)([A-Za-z0-9_.\-]*(?:password|passwd|pwd|secret|token|(?:api|access|secret|private|auth)[_.\-]?key|authorization))(\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+")


def redact(text: str) -> str:
    """Best-effort removal of credentials before text reaches the model, the logs or the audit trail."""
    text = _BEARER.sub("Bearer [REDACTED]", text)  # first, so a JWT after 'Authorization:' cannot survive
    return _SECRET.sub(r"\1\2[REDACTED]", text)


def read(runner: Runner, args: list[str], timeout: float = 30.0):
    """Run a READ-ONLY kubectl command; refuses anything the allowlist would reject."""
    chk = check_command(shlex.join(["kubectl", *args]))
    if not chk.ok:
        raise PermissionError(f"agent read blocked by allowlist: {' '.join(args)} ({chk.reason})")
    return runner.run(args, timeout=timeout)


@dataclass
class Problem:
    kind: str
    name: str  # the object that has the problem
    workload: str  # the deployment/service it belongs to (used to scope verification)
    detail: str = ""

    def key(self) -> tuple[str, str]:
        return (self.kind, self.workload)

    def line(self) -> str:
        return f"{self.kind} {self.name}: {self.detail}".strip()


@dataclass
class State:
    pods: list[dict] = field(default_factory=list)
    deployments: list[dict] = field(default_factory=list)
    replicasets: list[dict] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)
    endpoints: list[dict] = field(default_factory=list)

    def pod_labels(self) -> list[dict]:
        return [(p.get("metadata") or {}).get("labels") or {} for p in self.pods]


def collect_state(runner: Runner, ns: str) -> State:
    res = read(runner, ["get", "pods,deployments,replicasets,services,endpoints", "-n", ns, "-o", "json"])
    if not res.ok:
        raise RuntimeError(f"cannot read namespace '{ns}': {res.text[:200]}")
    st = State()
    for it in json.loads(res.stdout).get("items", []):
        {"Pod": st.pods, "Deployment": st.deployments, "ReplicaSet": st.replicasets,
         "Service": st.services, "Endpoints": st.endpoints}.get(it.get("kind"), []).append(it)
    return st


def _workload_of_pod(pod: dict) -> str:
    owners = (pod.get("metadata") or {}).get("ownerReferences") or []
    name = owners[0]["name"] if owners else (pod.get("metadata") or {}).get("name", "?")
    return name.rsplit("-", 1)[0] if owners and owners[0].get("kind") == "ReplicaSet" else name


def find_problems(st: State) -> list[Problem]:
    out: list[Problem] = []
    for pod in st.pods:
        meta, status = pod.get("metadata") or {}, pod.get("status") or {}
        if meta.get("deletionTimestamp") or status.get("phase") in ("Succeeded",):
            continue
        name, wl = meta.get("name", "?"), _workload_of_pod(pod)
        if status.get("phase") == "Pending":
            for c in status.get("conditions") or []:
                if c.get("type") == "PodScheduled" and c.get("status") == "False":
                    out.append(Problem("Unschedulable", name, wl, (c.get("message") or c.get("reason") or "")[:200]))
        for cs in status.get("containerStatuses") or []:
            waiting = (cs.get("state") or {}).get("waiting") or {}
            if waiting.get("reason") in BAD_WAITING:
                out.append(Problem(waiting["reason"], name, wl, f"container {cs.get('name')}: {waiting.get('message', '')}"[:200]))
            last = (cs.get("lastState") or {}).get("terminated") or {}
            if last.get("reason") == "OOMKilled" and not cs.get("ready"):
                out.append(Problem("OOMKilled", name, wl, f"container {cs.get('name')} exit code {last.get('exitCode')}"))
        ready = [c for c in status.get("conditions") or [] if c.get("type") == "Ready"]
        if status.get("phase") == "Running" and ready and ready[0].get("status") == "False":
            out.append(Problem("NotReady", name, wl, "pod is Running but not Ready (probe failing?)"))
    for d in st.deployments:
        name = (d.get("metadata") or {}).get("name", "?")
        want, have = (d.get("spec") or {}).get("replicas", 1), (d.get("status") or {}).get("availableReplicas") or 0
        if want and have < want:
            out.append(Problem("DeploymentUnavailable", name, name, f"{have}/{want} replicas available"))
        for c in (d.get("status") or {}).get("conditions") or []:
            if c.get("type") == "Progressing" and c.get("reason") == "ProgressDeadlineExceeded":
                out.append(Problem("ProgressDeadlineExceeded", name, name, (c.get("message") or "")[:200]))
    for rs in st.replicasets:
        for c in (rs.get("status") or {}).get("conditions") or []:
            if c.get("type") == "ReplicaFailure" and c.get("status") == "True":
                owners = (rs.get("metadata") or {}).get("ownerReferences") or []
                wl = owners[0]["name"] if owners else (rs.get("metadata") or {}).get("name", "?")
                out.append(Problem("ReplicaFailure", (rs.get("metadata") or {}).get("name", "?"), wl, (c.get("message") or "")[:200]))
    ready_eps = {}
    for ep in st.endpoints:
        n = (ep.get("metadata") or {}).get("name")
        ready_eps[n] = sum(len(s.get("addresses") or []) for s in ep.get("subsets") or [])
    for svc in st.services:
        name = (svc.get("metadata") or {}).get("name", "?")
        if (svc.get("spec") or {}).get("selector") and ready_eps.get(name, 0) == 0:
            out.append(Problem("ServiceNoEndpoints", name, name, f"selector {(svc['spec'])['selector']} has no ready endpoints"))
    uniq = {(p.kind, p.name): p for p in out}
    return sorted(uniq.values(), key=lambda p: (p.kind, p.name))


def _cap(text: str, head: int = 2500, tail: int = 2500) -> str:
    return text if len(text) <= head + tail else text[:head] + "\n...[truncated]...\n" + text[-tail:]


def observe(runner: Runner, ns: str, problems: list[Problem], max_pods: int = 3) -> str:
    """Evidence bundle for the planner. Treated as UNTRUSTED data downstream (logs and events can contain anything)."""
    parts = ["== problems detected ==", *([p.line() for p in problems] or ["(none)"])]

    def section(title: str, args: list[str], cap: bool = True, tail_lines: int | None = None) -> None:
        r = read(runner, args)
        text = redact(r.text)
        if tail_lines:
            text = "\n".join(text.splitlines()[-tail_lines:])
        parts.extend(["", f"== {title} ==", _cap(text) if cap else text])

    section("pods", ["get", "pods", "-n", ns, "-o", "wide"])
    section("events", ["get", "events", "-n", ns, "--sort-by=.lastTimestamp"], tail_lines=40)
    section("services and endpoints", ["get", "services,endpoints", "-n", ns])
    seen_pods: list[str] = []
    for p in problems:
        if p.name not in seen_pods and p.kind not in ("DeploymentUnavailable", "ProgressDeadlineExceeded", "ServiceNoEndpoints", "ReplicaFailure"):
            seen_pods.append(p.name)
    for pod in seen_pods[:max_pods]:
        section(f"describe pod {pod}", ["describe", "pod", pod, "-n", ns])
        section(f"logs {pod}", ["logs", pod, "-n", ns, "--all-containers", "--tail=30"], cap=False)
        section(f"previous logs {pod}", ["logs", pod, "-n", ns, "--all-containers", "--previous", "--tail=30"], cap=False)
    for d in sorted({p.workload for p in problems if p.kind in ("DeploymentUnavailable", "ProgressDeadlineExceeded", "ReplicaFailure")})[:2]:
        section(f"describe deployment {d}", ["describe", "deployment", d, "-n", ns])
    return "\n".join(parts)
