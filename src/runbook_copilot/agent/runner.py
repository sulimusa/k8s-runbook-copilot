"""How the agent talks to a cluster. The kube identity is chosen by the OPERATOR (kubeconfig/context), never by the
model, so what the agent can do is bounded by that identity's RBAC even if every other layer failed."""
from __future__ import annotations

import subprocess  # nosec B404
from dataclasses import dataclass
from typing import Protocol

MAX_OUTPUT = 40_000


@dataclass
class RunResult:
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def text(self) -> str:
        return self.stdout if self.ok else (self.stderr or self.stdout)


class Runner(Protocol):
    def run(self, args: list[str], timeout: float = 30.0) -> RunResult: ...


class KubectlRunner:
    """Runs kubectl with an argv list (never a shell string) pinned to one kubeconfig/context."""

    def __init__(self, context: str | None = None, kubeconfig: str | None = None):
        self.context = context
        self.kubeconfig = kubeconfig

    def _base(self) -> list[str]:
        argv = ["kubectl"]
        if self.kubeconfig:
            argv += ["--kubeconfig", self.kubeconfig]
        if self.context:
            argv += ["--context", self.context]
        return argv + ["--request-timeout=20s"]

    def run(self, args: list[str], timeout: float = 30.0) -> RunResult:
        argv = self._base() + args
        try:
            # argv list, no shell; args come from typed actions or fixed read templates
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)  # nosec B603
        except subprocess.TimeoutExpired:
            return RunResult(args, 124, "", f"timed out after {timeout}s")
        except FileNotFoundError as e:
            raise RuntimeError("kubectl not found on PATH") from e
        return RunResult(args, p.returncode, p.stdout[:MAX_OUTPUT], p.stderr[:MAX_OUTPUT])

    def current_context(self) -> str:
        base = ["kubectl"] + (["--kubeconfig", self.kubeconfig] if self.kubeconfig else [])
        try:
            p = subprocess.run(base + ["config", "current-context"], capture_output=True, text=True, check=False)  # nosec B603
        except FileNotFoundError as e:
            raise RuntimeError("kubectl not found on PATH") from e
        return self.context or p.stdout.strip()
