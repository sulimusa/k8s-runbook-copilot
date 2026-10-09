import copy
import json

import pytest
from conftest import FakeLLM
from fakecluster import FakeCluster, deployment, service

from runbook_copilot.agent.audit import AuditLog
from runbook_copilot.agent.loop import Agent
from runbook_copilot.agent.policy import Policy
from runbook_copilot.config import Settings

CITE = "k8s-docs:debug/crashloop#00"
INCIDENT = "pod keeps restarting CrashLoopBackOff"
OOM_QUOTE = "OOMKilled memhog-5f6d8-0: container stress exit code 137"


class Clock:
    """Fake time so verification polling (up to 120s) costs nothing."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def now(self):
        return self.t


class RecordingLLM(FakeLLM):
    def __init__(self, *r):
        super().__init__(*r)
        self.prompts: list[str] = []

    def __call__(self, messages):
        self.prompts.append("\n".join(m["content"] for m in messages))
        return super().__call__(messages)


def plan(action, quote=OOM_QUOTE, cites=(CITE,), fixable=True, rationale="docs and evidence support this"):
    return {"fixable": fixable, "rationale": rationale, "citations": list(cites), "evidence_quote": quote,
            "action": action, "expected_outcome": "pods become Ready"}


def oom_cluster(ns="lab-oom", labels=None):
    fc = FakeCluster(ns, ns_labels=labels)
    fc.add(deployment("memhog", "polinux/stress", ns, container="stress",
                      resources={"limits": {"memory": "100Mi"}, "requests": {"memory": "50Mi"}}), needs_memory="200Mi")
    fc.log_text = "stress: FAIL: (1) out of memory"
    return fc


def raise_memory(ns="lab-oom", limit="256Mi"):
    return {"type": "set_resources", "namespace": ns, "name": "memhog", "container": "stress", "memory_limit": limit}


@pytest.fixture
def mk(retriever, tmp_path):
    def _mk(fc, *plans, policy="dev", kube_context="kind-lab", audit=True, pol_override=None, llm=None):
        clock = Clock()
        s = Settings(log_path=tmp_path / "r.jsonl", min_bm25_score=0.1, min_query_coverage=0.05, llm_api_key="x")
        pol = pol_override or Policy.load(policy)
        llm = llm or RecordingLLM(*plans)
        ag = Agent(retriever, llm, pol, fc, settings=s, audit=AuditLog(tmp_path / "audit.jsonl") if audit else None,
                   kube_context=kube_context, sleep=clock.sleep, clock=clock.now)
        ag.llm_obj, ag.audit_path = llm, tmp_path / "audit.jsonl"
        return ag
    return _mk


# ---------------------------------------------------------------------------- the happy path (dev acts)
def test_dev_fixes_oomkilled_automatically_with_dry_run_first(mk):
    fc = oom_cluster()
    ag = mk(fc, plan(raise_memory()))
    rep = ag.run("lab-oom", INCIDENT)
    assert rep.status == "resolved" and rep.writes == 1 and rep.fixes_applied == 1 and rep.rollbacks == 0
    assert len(fc.writes) == 1 and "256Mi" in fc.writes[0][-1]
    patches = [c for c in fc.calls if c[0] == "patch"]
    assert "--dry-run=server" in patches[0] and "--dry-run=server" not in patches[1]  # validated server-side first
    assert fc.deployments["memhog"]["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "256Mi"
    events = [json.loads(line)["event"] for line in ag.audit_path.read_text().splitlines()]
    assert events[0] == "run_start" and events[-1] == "run_end" and {"plan", "policy", "apply", "verify"} <= set(events)
    assert rep.prompt_tokens == 0 and rep.proposal is None


def test_healthy_namespace_does_nothing_and_never_calls_the_llm(mk):
    fc = FakeCluster("lab-ok")
    fc.add(deployment("web", "nginx:1.27", "lab-ok"))
    ag = mk(fc, plan(raise_memory()))
    rep = ag.run("lab-ok", "all good?")
    assert rep.status == "no_problem" and ag.llm_obj.calls == 0 and fc.writes == []


# ---------------------------------------------------------------------------- prod: advise only
def test_prod_advises_and_never_writes(mk):
    fc = oom_cluster("prod", labels={})
    ag = mk(fc, plan(raise_memory("prod", "200Mi")), policy="prod", kube_context="prod-eks")
    rep = ag.run("prod", INCIDENT)
    assert rep.status == "advised" and fc.writes == [] and rep.writes == 0
    assert rep.proposal and "200Mi" in rep.proposal["command"] and rep.proposal["rollback"]
    assert not any("--dry-run=server" in c for c in fc.calls)  # prod identity gets no write-ish calls at all
    assert fc.deployments["memhog"]["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "100Mi"


def test_prod_proposals_are_still_bounds_checked(mk):
    fc = oom_cluster("prod", labels={})
    rep = mk(fc, plan(raise_memory("prod", "900Mi")), policy="prod", kube_context="prod-eks").run("prod", INCIDENT)
    assert rep.status == "denied" and "at most 2x" in rep.reason and fc.writes == []


# ---------------------------------------------------------------------------- refusals (no writes, minimal reads)
def test_unlabelled_namespace_is_refused(mk):
    fc = oom_cluster(labels={})
    rep = mk(fc, plan(raise_memory())).run("lab-oom", INCIDENT)
    assert rep.status == "denied" and "opt-in" in rep.reason
    assert fc.writes == [] and [c[:2] for c in fc.calls] == [["get", "namespace"]]


@pytest.mark.parametrize("ctx", ["prod-eks", "uat-1", "gke_staging", "", "random"])
def test_wrong_kube_context_is_refused_before_touching_the_cluster(mk, ctx):
    fc = oom_cluster()
    rep = mk(fc, plan(raise_memory()), kube_context=ctx).run("lab-oom", INCIDENT)
    assert rep.status == "denied" and fc.calls == []


def test_protected_namespace_is_refused(mk):
    fc = oom_cluster("kube-system")
    rep = mk(fc, plan(raise_memory("kube-system"))).run("kube-system", INCIDENT)
    assert rep.status == "denied" and fc.writes == []


@pytest.mark.parametrize("p,why", [
    (plan(raise_memory(), quote="this sentence never appears in the cluster output"), "verbatim"),
    (plan(raise_memory(), quote="short"), "verbatim"),
    (plan(raise_memory(), cites=("k8s-docs:made/up#99",)), "citation"),
    (plan(raise_memory(), cites=()), "citation"),
])
def test_ungrounded_proposals_are_refused(mk, p, why):
    fc = oom_cluster()
    rep = mk(fc, p).run("lab-oom", INCIDENT)
    assert rep.status == "denied" and why in rep.reason and fc.writes == []


def test_policy_bound_violation_is_refused(mk):
    fc = oom_cluster()
    rep = mk(fc, plan(raise_memory(limit="900Mi"))).run("lab-oom", INCIDENT)
    assert rep.status == "denied" and "at most 4x" in rep.reason and fc.writes == []


def test_action_in_another_namespace_is_refused(mk):
    fc = oom_cluster()
    rep = mk(fc, plan(raise_memory("kube-system"))).run("lab-oom", INCIDENT)
    assert rep.status == "denied" and "kube-system" in rep.reason and fc.writes == []


def test_missing_target_is_refused(mk):
    fc = oom_cluster()
    a = raise_memory()
    a["name"] = "ghost"
    rep = mk(fc, plan(a)).run("lab-oom", INCIDENT)
    assert rep.status == "denied" and "not found" in rep.reason and fc.writes == []


def test_invalid_model_output_never_reaches_the_cluster(mk):
    fc = oom_cluster()
    rep = mk(fc, "this is not json").run("lab-oom", INCIDENT)
    assert rep.status == "error" and fc.writes == []
    rep = mk(fc, plan({"type": "exec", "namespace": "lab-oom", "name": "x"})).run("lab-oom", INCIDENT)
    assert rep.status == "error" and fc.writes == []


def test_dry_run_rejection_stops_before_any_write(mk):
    fc = oom_cluster()
    fc.fail_dry_run = True
    rep = mk(fc, plan(raise_memory())).run("lab-oom", INCIDENT)
    assert rep.status == "error" and "dry-run" in rep.reason and fc.writes == []


# ---------------------------------------------------------------------------- escalation: not everything is fixable
def test_unfixable_problem_is_escalated_not_guessed(mk):
    fc = FakeCluster("lab-crash")
    fc.add(deployment("crashy", "busybox:1.36", "lab-crash"), always_crash=True)
    fc.log_text = "FATAL: missing DATABASE_URL"
    p = plan(None, fixable=False, rationale="needs a DATABASE_URL value that only a human can provide")
    rep = mk(fc, p).run("lab-crash", INCIDENT)
    assert rep.status == "escalated" and "DATABASE_URL" in rep.reason and fc.writes == []


# ---------------------------------------------------------------------------- verification and rollback
def test_failed_fix_is_rolled_back_then_the_next_plan_succeeds(mk):
    fc = oom_cluster()
    useless = {"type": "scale_deployment", "namespace": "lab-oom", "name": "memhog", "replicas": 2}
    ag = mk(fc, plan(useless), plan(raise_memory()))
    rep = ag.run("lab-oom", INCIDENT)
    assert rep.status == "resolved" and rep.rollbacks == 1 and rep.writes == 2 and rep.fixes_applied == 1
    scales = [w for w in fc.writes if w[0] == "scale"]
    assert [s[2] for s in scales] == ["--replicas=2", "--replicas=1"]  # applied, then restored
    assert fc.deployments["memhog"]["spec"]["replicas"] == 1
    assert any("already tried" in p or "scale_deployment" in p for p in ag.llm_obj.prompts[1:])  # planner told what failed


def test_repeating_a_rolled_back_action_is_refused(mk):
    fc = oom_cluster()
    useless = {"type": "scale_deployment", "namespace": "lab-oom", "name": "memhog", "replicas": 2}
    rep = mk(fc, plan(useless)).run("lab-oom", INCIDENT)  # the fake LLM keeps returning the same plan
    assert rep.status == "denied" and "already tried" in rep.reason
    assert rep.rollbacks == 1 and rep.fixes_applied == 0 and fc.deployments["memhog"]["spec"]["replicas"] == 1


def test_rollback_restores_a_removed_field(mk):
    fc = oom_cluster()
    bad = {"type": "set_resources", "namespace": "lab-oom", "name": "memhog", "container": "stress", "cpu_request": "100m"}
    ag = mk(fc, plan(bad), plan(raise_memory()))
    rep = ag.run("lab-oom", INCIDENT)
    res = fc.deployments["memhog"]["spec"]["template"]["spec"]["containers"][0]["resources"]
    assert rep.rollbacks == 1 and "cpu" not in res.get("requests", {})  # the cpu request that did not exist is gone again
    assert res["limits"]["memory"] == "256Mi" and rep.status == "resolved"


# ---------------------------------------------------------------------------- more scenarios
def test_failed_rollout_is_fixed_with_rollout_undo(mk):
    fc = FakeCluster("lab-roll")
    good = deployment("shop", "nginx:1.27", "lab-roll", replicas=2)
    fc.add(deployment("shop", "nginx:1.27-does-not-exist", "lab-roll", replicas=2))
    fc.flags["shop"]["prev"] = copy.deepcopy(good["spec"])
    quote = "ImagePullBackOff shop-5f6d8-0: container app: Back-off pulling image"
    rep = mk(fc, plan({"type": "rollout_undo", "namespace": "lab-roll", "name": "shop"}, quote=quote)).run("lab-roll", INCIDENT)
    assert rep.status == "resolved" and fc.writes == [["rollout", "undo", "deployment/shop", "-n", "lab-roll"]]


def test_service_selector_typo_is_fixed_and_a_wrong_selector_is_refused(mk):
    def cluster():
        fc = FakeCluster("lab-dns")
        fc.add(deployment("web", "nginx:1.27", "lab-dns", replicas=2))
        fc.services["web"] = service("web", {"app": "wbe"}, "lab-dns")
        return fc

    quote = "ServiceNoEndpoints web: selector {'app': 'wbe'} has no ready endpoints"
    good = {"type": "patch_service_selector", "namespace": "lab-dns", "name": "web", "selector": {"app": "web"}}
    fc = cluster()
    rep = mk(fc, plan(good, quote=quote)).run("lab-dns", INCIDENT)
    assert rep.status == "resolved" and fc.services["web"]["spec"]["selector"] == {"app": "web"}

    fc = cluster()
    wrong = dict(good, selector={"app": "nonexistent"})
    rep = mk(fc, plan(wrong, quote=quote)).run("lab-dns", INCIDENT)
    assert rep.status == "denied" and "no existing pod" in rep.reason and fc.writes == []


def _probe_cluster(ns="lab-probe"):
    fc = FakeCluster(ns)
    for n in ("probe1", "probe2"):
        fc.add(deployment(n, "nginx:1.27", ns, container="web", ports=[80],
                          readiness={"httpGet": {"path": "/", "port": 8080}}))
    return fc


def _probe_plan(n, ns="lab-probe"):
    return plan({"type": "patch_probe", "namespace": ns, "name": n, "container": "web", "probe": "readiness", "port": 80},
                quote=f"NotReady {n}-5f6d8-0: pod is Running but not Ready (probe failing?)")


def test_two_unhealthy_workloads_are_fixed_in_sequence(mk):
    fc = _probe_cluster()
    rep = mk(fc, _probe_plan("probe1"), _probe_plan("probe2")).run("lab-probe", INCIDENT)
    assert rep.status == "resolved" and rep.writes == 2 and rep.fixes_applied == 2 and rep.rollbacks == 0


def test_write_budget_stops_the_run_with_a_partial_result(mk):
    fc = _probe_cluster()
    one_write = Policy({**Policy.load("dev").data, "max_writes_per_run": 1})
    rep = mk(fc, _probe_plan("probe1"), _probe_plan("probe2"), pol_override=one_write).run("lab-probe", INCIDENT)
    assert rep.status == "partially_resolved" and "budget" in rep.reason and rep.fixes_applied == 1
    assert len(fc.writes) == 1 and rep.problems_after  # one workload fixed, the other still unhealthy


# ---------------------------------------------------------------------------- secrets, telemetry
def test_secrets_never_reach_the_model_or_the_audit_trail(mk):
    fc = oom_cluster()
    fc.log_text = "starting with DB_PASSWORD=hunter2 and Authorization: Bearer eyJsecret.jwt.sig"
    llm = RecordingLLM(plan(raise_memory()))
    ag = mk(fc, llm=llm)
    rep = ag.run("lab-oom", "pod restarts CrashLoopBackOff token=abc-secret-123")
    blob = "\n".join(llm.prompts) + ag.audit_path.read_text() + rep.model_dump_json()
    for leak in ("hunter2", "eyJsecret", "abc-secret-123"):
        assert leak not in blob, leak


def test_agent_metrics_are_emitted(retriever, tmp_path):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider

    from runbook_copilot.telemetry import Telemetry

    reader = InMemoryMetricReader()
    s = Settings(log_path=tmp_path / "r.jsonl", min_bm25_score=0.1, min_query_coverage=0.05, llm_api_key="x")
    tel = Telemetry(s, TracerProvider(), MeterProvider(metric_readers=[reader]))
    clock, fc = Clock(), oom_cluster()
    Agent(retriever, FakeLLM(plan(raise_memory())), Policy.load("dev"), fc, settings=s, telemetry=tel,
          kube_context="kind-lab", sleep=clock.sleep, clock=clock.now).run("lab-oom", INCIDENT)
    names = {m.name: m.data.data_points for rm in reader.get_metrics_data().resource_metrics
             for sm in rm.scope_metrics for m in sm.metrics}
    assert names["copilot.agent.runs"][0].attributes["status"] == "resolved"
    decisions = {dp.attributes["decision"] for dp in names["copilot.agent.actions"]}
    assert {"allow", "applied_ok"} <= decisions
