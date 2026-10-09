"""Typed fix actions. The model may only PROPOSE one of these (as JSON); it never writes a command.

Our code builds the kubectl argv from validated fields, so there is no shell, no free-form flags, and no way
for model output to smuggle in `--force`, `-o`, `--all` or a second command. Every field is validated against
Kubernetes naming rules (they must start with an alphanumeric, which also blocks flag injection like `-rf`).
"""
from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .quantities import parse_cpu, parse_memory

_DNS = re.compile(r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$")
_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/:@]*$")
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._\-/]*[A-Za-z0-9])?$")
_PATH = re.compile(r"^/[A-Za-z0-9._~\-/%?=&]*$")


def _dns(v: str) -> str:
    if len(v) > 253 or not _DNS.match(v):
        raise ValueError(f"invalid Kubernetes name: {v!r}")
    return v


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    namespace: str

    @field_validator("namespace")
    @classmethod
    def _ns(cls, v: str) -> str:
        return _dns(v)


class ScaleDeployment(_Base):
    type: Literal["scale_deployment"]
    name: str
    replicas: int = Field(ge=0, le=1000)
    _n = field_validator("name")(lambda cls, v: _dns(v))


class RolloutRestart(_Base):
    type: Literal["rollout_restart"]
    name: str
    _n = field_validator("name")(lambda cls, v: _dns(v))


class RolloutUndo(_Base):
    type: Literal["rollout_undo"]
    name: str
    _n = field_validator("name")(lambda cls, v: _dns(v))


class SetResources(_Base):
    type: Literal["set_resources"]
    name: str
    container: str
    memory_limit: str | None = None
    memory_request: str | None = None
    cpu_request: str | None = None
    _n = field_validator("name", "container")(lambda cls, v: _dns(v))

    @field_validator("memory_limit", "memory_request")
    @classmethod
    def _mem(cls, v: str | None) -> str | None:
        parse_memory(v)
        return v

    @field_validator("cpu_request")
    @classmethod
    def _cpu(cls, v: str | None) -> str | None:
        parse_cpu(v)
        return v


class SetImage(_Base):
    type: Literal["set_image"]
    name: str
    container: str
    image: str
    _n = field_validator("name", "container")(lambda cls, v: _dns(v))

    @field_validator("image")
    @classmethod
    def _img(cls, v: str) -> str:
        if len(v) > 300 or not _IMAGE.match(v):
            raise ValueError(f"invalid image reference: {v!r}")
        return v


class PatchServiceSelector(_Base):
    type: Literal["patch_service_selector"]
    name: str
    selector: dict[str, str] = Field(min_length=1, max_length=5)
    _n = field_validator("name")(lambda cls, v: _dns(v))

    @field_validator("selector")
    @classmethod
    def _sel(cls, v: dict[str, str]) -> dict[str, str]:
        for k, val in v.items():
            if not _LABEL.match(k) or not _LABEL.match(val) or len(k) > 253 or len(val) > 63:
                raise ValueError(f"invalid selector label: {k}={val}")
        return v


class PatchProbe(_Base):
    type: Literal["patch_probe"]
    name: str
    container: str
    probe: Literal["readiness", "liveness", "startup"]
    port: int | None = Field(default=None, ge=1, le=65535)
    path: str | None = None
    _n = field_validator("name", "container")(lambda cls, v: _dns(v))

    @field_validator("path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        if v is not None and (len(v) > 200 or not _PATH.match(v)):
            raise ValueError(f"invalid probe path: {v!r}")
        return v


class DeletePod(_Base):
    type: Literal["delete_pod"]
    name: str
    _n = field_validator("name")(lambda cls, v: _dns(v))


Action = Annotated[
    Union[ScaleDeployment, RolloutRestart, RolloutUndo, SetResources, SetImage, PatchServiceSelector, PatchProbe, DeletePod],
    Field(discriminator="type"),
]

ACTION_TYPES = ["scale_deployment", "rollout_restart", "rollout_undo", "set_resources", "set_image",
                "patch_service_selector", "patch_probe", "delete_pod"]
# Actions whose argv supports `--dry-run=server` (so the API server validates before we apply for real).
DRY_RUN_TYPES = {"scale_deployment", "set_resources", "set_image", "patch_service_selector", "patch_probe"}


def target_ref(a: Any) -> tuple[str, str]:
    """(kubectl kind, name) of the object the action modifies."""
    if a.type == "patch_service_selector":
        return "service", a.name
    if a.type == "delete_pod":
        return "pod", a.name
    return "deployment", a.name


def _j(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"))


def build_argv(a: Any, *, dry_run: bool = False) -> list[str]:
    """kubectl arguments (without the leading `kubectl` and without context flags) for an action."""
    ns = ["-n", a.namespace]
    dry = ["--dry-run=server"] if dry_run else []
    if a.type == "scale_deployment":
        return ["scale", f"deployment/{a.name}", f"--replicas={a.replicas}", *ns, *dry]
    if a.type == "rollout_restart":
        return ["rollout", "restart", f"deployment/{a.name}", *ns]
    if a.type == "rollout_undo":
        return ["rollout", "undo", f"deployment/{a.name}", *ns]
    if a.type == "set_resources":
        res: dict[str, Any] = {}
        if a.memory_limit:
            res["limits"] = {"memory": a.memory_limit}
        req = {k: v for k, v in (("memory", a.memory_request), ("cpu", a.cpu_request)) if v}
        if req:
            res["requests"] = req
        return ["patch", "deployment", a.name, *ns, "--type=strategic", *dry,
                "-p", _j({"spec": {"template": {"spec": {"containers": [{"name": a.container, "resources": res}]}}}})]
    if a.type == "set_image":
        return ["patch", "deployment", a.name, *ns, "--type=strategic", *dry,
                "-p", _j({"spec": {"template": {"spec": {"containers": [{"name": a.container, "image": a.image}]}}}})]
    if a.type == "patch_service_selector":
        return ["patch", "service", a.name, *ns, "--type=json", *dry,
                "-p", _j([{"op": "replace", "path": "/spec/selector", "value": a.selector}])]
    if a.type == "patch_probe":
        http: dict[str, Any] = {}
        if a.port is not None:
            http["port"] = a.port
        if a.path is not None:
            http["path"] = a.path
        return ["patch", "deployment", a.name, *ns, "--type=strategic", *dry,
                "-p", _j({"spec": {"template": {"spec": {"containers": [
                    {"name": a.container, f"{a.probe}Probe": {"httpGet": http}}]}}}})]
    if a.type == "delete_pod":
        return ["delete", "pod", a.name, *ns, "--wait=false"]
    raise ValueError(f"unknown action type: {a.type}")


def _container(obj: dict, name: str) -> tuple[int, dict] | tuple[None, None]:
    for i, c in enumerate(((obj.get("spec") or {}).get("template") or {}).get("spec", {}).get("containers", [])):
        if c.get("name") == name:
            return i, c
    return None, None


def plan_rollback(a: Any, before: dict) -> list[list[str]]:
    """kubectl argv lists that restore the pre-change state, derived from the object's JSON captured BEFORE the write.
    Empty list means the action is idempotent or self-healing (restart, pod delete)."""
    ns = ["-n", a.namespace]
    if a.type == "scale_deployment":
        old = (before.get("spec") or {}).get("replicas")
        return [["scale", f"deployment/{a.name}", f"--replicas={old}", *ns]] if old is not None else []
    if a.type == "rollout_undo":
        return [["rollout", "undo", f"deployment/{a.name}", *ns]]
    if a.type == "set_resources":
        _, c = _container(before, a.container)
        old = (c or {}).get("resources") or {}
        res: dict[str, Any] = {}
        if a.memory_limit:
            res.setdefault("limits", {})["memory"] = (old.get("limits") or {}).get("memory")
        for k, new in (("memory", a.memory_request), ("cpu", a.cpu_request)):
            if new:
                res.setdefault("requests", {})[k] = (old.get("requests") or {}).get(k)  # None removes the field
        return [["patch", "deployment", a.name, *ns, "--type=strategic", "-p",
                 _j({"spec": {"template": {"spec": {"containers": [{"name": a.container, "resources": res}]}}}})]]
    if a.type == "set_image":
        _, c = _container(before, a.container)
        old_img = (c or {}).get("image")
        return [["patch", "deployment", a.name, *ns, "--type=strategic", "-p",
                 _j({"spec": {"template": {"spec": {"containers": [{"name": a.container, "image": old_img}]}}}})]] if old_img else []
    if a.type == "patch_service_selector":
        old_sel = (before.get("spec") or {}).get("selector")
        return [["patch", "service", a.name, *ns, "--type=json", "-p",
                 _j([{"op": "replace", "path": "/spec/selector", "value": old_sel}])]] if old_sel else []
    if a.type == "patch_probe":
        idx, c = _container(before, a.container)
        if idx is None:
            return []
        key = f"{a.probe}Probe"
        path = f"/spec/template/spec/containers/{idx}/{key}"
        op = {"op": "replace", "path": path, "value": c[key]} if c.get(key) else {"op": "remove", "path": path}
        return [["patch", "deployment", a.name, *ns, "--type=json", "-p", _j([op])]]
    return []
