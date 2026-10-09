"""The RBAC manifests must (a) grant exactly what the agent's code needs and (b) deny everything else that matters."""
from pathlib import Path

import yaml

DOCS = list(yaml.safe_load_all((Path(__file__).parents[1] / "deploy/rbac/agent-rbac.yaml").read_text()))
ROLES = {d["metadata"]["name"]: d["rules"] for d in DOCS if d["kind"] == "ClusterRole"}


def allows(role_names, verb, group, resource):
    return any(verb in r["verbs"] and group in r["apiGroups"] and resource in r["resources"]
               for n in role_names for r in ROLES[n])


READONLY = ["copilot-agent-ns-reader", "copilot-agent-reader"]
DEV = READONLY + ["copilot-agent-writer"]

# (verb, apiGroup, resource) tuples kubectl needs for every READ the agent performs (see health.py)
NEEDED_READS = [("get", "", "namespaces"), ("list", "", "pods"), ("list", "apps", "deployments"), ("list", "apps", "replicasets"),
                ("list", "", "services"), ("list", "", "endpoints"), ("list", "", "events"), ("get", "", "pods"),
                ("get", "", "pods/log"), ("get", "apps", "deployments"), ("get", "", "services"), ("get", "apps", "replicasets")]
# ... and for every typed WRITE (see actions.py): patch/restart/undo/set_*, scale, selector patch, delete pod
NEEDED_WRITES = [("patch", "apps", "deployments"), ("patch", "", "services"), ("delete", "", "pods"),
                 ("get", "apps", "deployments/scale"), ("patch", "apps", "deployments/scale"), ("update", "apps", "deployments/scale")]
WRITE_VERBS = ("create", "update", "patch", "delete", "deletecollection", "escalate", "bind", "impersonate", "*")


def test_both_identities_cover_every_read_the_agent_performs():
    for ident in (READONLY, DEV):
        for v, g, r in NEEDED_READS:
            assert allows(ident, v, g, r), (v, g, r)


def test_dev_identity_covers_every_typed_write():
    for v, g, r in NEEDED_WRITES:
        assert allows(DEV, v, g, r), (v, g, r)


def test_readonly_identity_cannot_write_anything_or_read_secrets():
    for res_group in (("", "pods"), ("apps", "deployments"), ("", "services"), ("", "secrets"), ("", "namespaces"),
                      ("rbac.authorization.k8s.io", "rolebindings"), ("", "pods/exec"), ("apps", "deployments/scale")):
        for verb in WRITE_VERBS:
            assert not allows(READONLY, verb, *res_group), (verb, res_group)
    for secret_like in ("secrets", "configmaps", "pods/exec", "pods/portforward", "serviceaccounts/token"):
        assert not allows(READONLY, "get", "", secret_like), secret_like


def test_dev_identity_stays_narrow():
    for bad in [("get", "", "secrets"), ("list", "", "secrets"), ("get", "", "configmaps"), ("create", "", "pods/exec"),
                ("create", "apps", "deployments"), ("delete", "apps", "deployments"), ("delete", "", "namespaces"),
                ("patch", "", "namespaces"), ("create", "rbac.authorization.k8s.io", "rolebindings"),
                ("patch", "rbac.authorization.k8s.io", "clusterroles"), ("delete", "", "services"), ("create", "", "pods"),
                ("patch", "", "pods"), ("patch", "", "nodes"), ("patch", "", "resourcequotas"), ("create", "", "serviceaccounts/token")]:
        assert not allows(DEV, *bad), bad


def test_no_wildcards_anywhere():
    for name, rules in ROLES.items():
        for r in rules:
            for key in ("apiGroups", "resources", "verbs"):
                assert "*" not in r[key], (name, key)


def test_namespaced_roles_are_not_bound_cluster_wide():
    for d in DOCS:
        if d["kind"] == "ClusterRoleBinding":
            assert d["roleRef"]["name"] == "copilot-agent-ns-reader", d["metadata"]["name"]  # only namespace labels are cluster-wide
