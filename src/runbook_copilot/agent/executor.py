"""The only code path that writes to a cluster. It refuses to run without an explicit `allow` decision."""
from __future__ import annotations

from typing import Any

from .actions import DRY_RUN_TYPES, build_argv
from .policy import Decision
from .runner import Runner, RunResult


class Executor:
    def __init__(self, runner: Runner):
        self.runner = runner

    def dry_run(self, action: Any, decision: Decision) -> RunResult | None:
        """Server-side validation for actions that support it; None means the action type has no dry-run."""
        self._require(decision)
        if action.type not in DRY_RUN_TYPES:
            return None
        return self.runner.run(build_argv(action, dry_run=True))

    def apply(self, action: Any, decision: Decision) -> RunResult:
        self._require(decision)
        return self.runner.run(build_argv(action))

    def rollback(self, argv_lists: list[list[str]]) -> list[RunResult]:
        return [self.runner.run(a) for a in argv_lists]

    @staticmethod
    def _require(decision: Decision) -> None:
        if not decision.allowed:
            raise PermissionError(f"refusing to write without an 'allow' decision (got '{decision.outcome}': {decision.reason})")
