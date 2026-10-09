"""A small simulated Kubernetes for testing the agent loop offline.

It stores real-shaped Deployment/Service JSON, understands the exact kubectl argv our code emits (reads and the
typed-action writes), applies strategic-merge / JSON patches, models `rollout undo`, and derives pod health from the
spec so that a correct fix really changes what the next read returns. It is a TEST DOUBLE: it validates our logic,
not real cluster behaviour (that needs the kind lab).
"""
from __future__ import annotations

import copy
import json

from runbook_copilot.agent.quantities import parse_cpu, parse_memory
from runbook_copilot.agent.runner import RunResult


def merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if v is None:
            dst.pop(k, None)
        elif isinstance(v, dict):
            merge(dst.setdefault(k, {}), v)
        else:
            dst[k] = v


def deployment(name, image, ns, labels=None, replicas=1, container="app", resources=None, ports=None, readiness=None,
               liveness=None):
    labels = labels or {"app": name}
    c = {"name": container, "image": image}
    if resources:
        c["resources"] = resources
    if ports:
        c["ports"] = [{"containerPort": p} for p in ports]
    if readiness:
        c["readinessProbe"] = readiness
    if liveness:
        c["livenessProbe"] = liveness
    return {"kind": "Deployment", "metadata": {"name": name, "namespace": ns},
            "spec": {"replicas": replicas, "selector": {"matchLabels": labels},
                     "template": {"metadata": {"labels": labels}, "spec": {"containers": [c]}}}}


class FakeCluster:
    WRITE_VERBS = ("patch", "scale", "delete")

    def __init__(self, ns="lab-x", ns_labels=None):
        self.ns = ns
        self.ns_labels = {"runbook-copilot/agent": "allowed"} if ns_labels is None else ns_labels
        self.deployments: dict[str, dict] = {}
        self.flags: dict[str, dict] = {}  # per-deployment failure model
        self.services: dict[str, dict] = {}
        self.calls: list[list[str]] = []
        self.writes: list[list[str]] = []
        self.fail_dry_run = False
        self.log_text = ""
        self.event_text = "LAST SEEN   TYPE      REASON   OBJECT   MESSAGE\n"

    # ---------------------------------------------------------------- model
    def add(self, dep: dict, **flags):
        name = dep["metadata"]["name"]
        self.deployments[name] = dep
        self.flags[name] = flags

    def _fault(self, name: str) -> str | None:
        dep, fl = self.deployments[name], self.flags[name]
        c = dep["spec"]["template"]["spec"]["containers"][0]
        if fl.get("always_crash"):
            return "crashloop"
        if "does-not-exist" in c["image"]:
            return "imagepull"
        mem = parse_memory(((c.get("resources") or {}).get("limits") or {}).get("memory"))
        if fl.get("needs_memory") and (mem or 0) < parse_memory(fl["needs_memory"]):
            return "oom"
        cpu = parse_cpu(((c.get("resources") or {}).get("requests") or {}).get("cpu"))
        if fl.get("max_cpu") and cpu and cpu > parse_cpu(fl["max_cpu"]):
            return "unschedulable"
        rp = (c.get("readinessProbe") or {}).get("httpGet") or {}
        declared = [p["containerPort"] for p in c.get("ports", [])]
        if rp and declared and rp.get("port") not in declared:
            return "notready"
        lp = (c.get("livenessProbe") or {}).get("httpGet") or {}
        if lp and fl.get("valid_paths") and lp.get("path") not in fl["valid_paths"]:
            return "crashloop"
        return None

    def _pods(self) -> list[dict]:
        pods = []
        for name, dep in self.deployments.items():
            fault, labels = self._fault(name), dep["spec"]["template"]["metadata"]["labels"]
            cname = dep["spec"]["template"]["spec"]["containers"][0]["name"]
            for i in range(dep["spec"]["replicas"]):
                status: dict = {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}],
                                "containerStatuses": [{"name": cname, "ready": True, "restartCount": 0,
                                                       "state": {"running": {}}}]}
                if fault == "imagepull":
                    status = {"phase": "Pending", "conditions": [{"type": "Ready", "status": "False"}],
                              "containerStatuses": [{"name": cname, "ready": False, "restartCount": 0,
                                                     "state": {"waiting": {"reason": "ImagePullBackOff", "message": "Back-off pulling image"}}}]}
                elif fault == "crashloop":
                    status["containerStatuses"][0].update(ready=False, restartCount=5,
                                                          state={"waiting": {"reason": "CrashLoopBackOff"}})
                    status["conditions"][0]["status"] = "False"
                elif fault == "oom":
                    status["containerStatuses"][0].update(
                        ready=False, restartCount=7, state={"waiting": {"reason": "CrashLoopBackOff"}},
                        lastState={"terminated": {"reason": "OOMKilled", "exitCode": 137}})
                    status["conditions"][0]["status"] = "False"
                elif fault == "unschedulable":
                    status = {"phase": "Pending", "conditions": [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable",
                                                                  "message": "0/2 nodes are available: Insufficient cpu."}]}
                elif fault == "notready":
                    status["conditions"][0]["status"] = "False"
                    status["containerStatuses"][0]["ready"] = False
                pods.append({"kind": "Pod", "metadata": {"name": f"{name}-5f6d8-{i}", "namespace": self.ns, "labels": dict(labels),
                                                          "ownerReferences": [{"kind": "ReplicaSet", "name": f"{name}-5f6d8"}]},
                             "status": status, "_healthy": fault is None})
        return pods

    def _dep_view(self, name: str) -> dict:
        d = copy.deepcopy(self.deployments[name])
        healthy = 0 if self._fault(name) else d["spec"]["replicas"]
        d["status"] = {"availableReplicas": healthy, "conditions": []}
        return d

    def _endpoints(self) -> list[dict]:
        pods = [p for p in self._pods() if p["_healthy"]]
        out = []
        for name, svc in self.services.items():
            sel = svc["spec"]["selector"]
            addrs = [{"ip": f"10.0.0.{i}"} for i, p in enumerate(pods) if all(p["metadata"]["labels"].get(k) == v for k, v in sel.items())]
            out.append({"kind": "Endpoints", "metadata": {"name": name}, "subsets": [{"addresses": addrs}] if addrs else []})
        return out

    # ---------------------------------------------------------------- kubectl
    def run(self, args: list[str], timeout: float = 30.0) -> RunResult:
        self.calls.append(list(args))
        if (args[0] in self.WRITE_VERBS or args[:2] in (["rollout", "undo"], ["rollout", "restart"])) \
                and "--dry-run=server" not in args:
            self.writes.append(list(args))  # real writes only; server-side dry runs change nothing
        try:
            return self._dispatch(args)
        except KeyError as e:
            return RunResult(args, 1, "", f'Error from server (NotFound): {e} not found')

    def _ok(self, args, out=""):
        return RunResult(args, 0, out if isinstance(out, str) else json.dumps(out), "")

    def _dispatch(self, a: list[str]) -> RunResult:
        verb = a[0]
        dry = "--dry-run=server" in a
        if verb == "get":
            what = a[1]
            if what == "namespace":
                return self._ok(a, {"metadata": {"name": a[2], "labels": self.ns_labels}})
            if what.startswith("pods,"):
                items = [{k: v for k, v in p.items() if k != "_healthy"} for p in self._pods()]
                items += [self._dep_view(n) for n in self.deployments]
                items += [{"kind": "ReplicaSet", "metadata": {"name": f"{n}-5f6d8", "ownerReferences": [{"name": n}]}, "status": {}}
                          for n in self.deployments]
                items += [dict(s, kind="Service") for s in self.services.values()] + self._endpoints()
                return self._ok(a, {"items": items})
            if what == "deployment":
                return self._ok(a, self._dep_view(a[2]))
            if what == "service":
                return self._ok(a, dict(self.services[a[2]], kind="Service"))
            if what == "pod":
                name = a[2]
                pod = next(p for p in self._pods() if p["metadata"]["name"] == name)
                return self._ok(a, {k: v for k, v in pod.items() if k != "_healthy"})
            if what == "events":
                return self._ok(a, self.event_text)
            return self._ok(a, f"NAME   READY   STATUS\n(fake {what})\n")
        if verb == "describe":
            return self._ok(a, f"Name: {a[2]}\nEvents:\n  {self.event_text}")
        if verb == "logs":
            return self._ok(a, self.log_text)
        if verb == "patch":
            kind, name = a[1], a[2]
            ptype = next(x.split("=", 1)[1] for x in a if x.startswith("--type="))
            body = json.loads(a[a.index("-p") + 1])
            if dry:
                if self.fail_dry_run:
                    return RunResult(a, 1, "", "admission webhook denied the request")
                return self._ok(a, f"{kind}/{name} patched (dry run)")
            if kind == "deployment":
                dep = self.deployments[name]
                self.flags[name]["prev"] = copy.deepcopy(dep["spec"])
                if ptype == "strategic":
                    for cp in body["spec"]["template"]["spec"]["containers"]:
                        c = next(c for c in dep["spec"]["template"]["spec"]["containers"] if c["name"] == cp["name"])
                        merge(c, {k: v for k, v in cp.items() if k != "name"})
                else:
                    self._json_patch(dep, body)
            else:
                self._json_patch(self.services[name], body)
            return self._ok(a, f"{kind}/{name} patched")
        if verb == "scale":
            name = a[1].split("/")[1]
            n = int(next(x for x in a if x.startswith("--replicas=")).split("=")[1])
            if not dry:
                self.flags[name]["prev"] = copy.deepcopy(self.deployments[name]["spec"])
                self.deployments[name]["spec"]["replicas"] = n
            return self._ok(a, f"deployment/{name} scaled")
        if verb == "rollout":
            name = a[2].split("/")[1]
            if a[1] == "undo":
                prev = self.flags[name].get("prev")
                if prev is None:
                    return RunResult(a, 1, "", "no rollout history found")
                self.flags[name]["prev"], self.deployments[name]["spec"] = copy.deepcopy(self.deployments[name]["spec"]), prev
            return self._ok(a, f"deployment/{name} rolled")
        if verb == "delete":
            return self._ok(a, f"pod {a[2]} deleted")
        return RunResult(a, 1, "", f"fake cluster: unsupported command {a}")

    @staticmethod
    def _json_patch(obj: dict, ops: list[dict]) -> None:
        for op in ops:
            parts = [p for p in op["path"].split("/") if p]
            cur = obj
            for p in parts[:-1]:
                cur = cur[int(p)] if isinstance(cur, list) else cur[p]
            last = parts[-1]
            if op["op"] == "replace":
                cur[int(last) if isinstance(cur, list) else last] = op["value"]
            elif op["op"] == "remove":
                cur.pop(last)


def service(name, selector, ns="lab-x"):
    return {"kind": "Service", "metadata": {"name": name, "namespace": ns}, "spec": {"selector": selector}}
