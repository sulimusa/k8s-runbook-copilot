"""The agent loop: observe -> retrieve -> plan -> ground -> policy -> (dry-run -> apply -> verify -> rollback) -> report.

Design rules
  * The LLM only ever returns a PlanAction (typed JSON). It never produces a command line.
  * Every write needs: a retrieved documentation citation AND a verbatim quote from live evidence AND a policy 'allow'.
  * dev (mode=act) applies automatically; prod (mode=advise) records the proposal and executes nothing.
  * After a write, success means the TARGET workload's problems are gone without new ones; otherwise roll back.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..config import Settings, get_settings
from ..llm.client import LLM, generate_model
from ..retrieval.search import Retriever, evaluate_gate
from ..telemetry import Telemetry, get_telemetry
from .actions import Action, build_argv, plan_rollback, target_ref
from .audit import AuditLog
from .executor import Executor
from .health import Problem, State, collect_state, find_problems, observe, read, redact
from .policy import Context, Decision, Policy
from .prompts import build_messages
from .runner import Runner


class PlanAction(BaseModel):
    fixable: bool
    rationale: str = ""
    citations: list[str] = Field(default_factory=list)
    evidence_quote: str = ""
    action: Action | None = None
    expected_outcome: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> PlanAction:
        if self.fixable and self.action is None:
            raise ValueError("fixable=true requires an action")
        return self


class AgentReport(BaseModel):
    run_id: str
    environment: str
    mode: str
    namespace: str
    incident: str
    # resolved | partially_resolved | not_resolved | advised | needs_approval | denied | escalated | no_problem | error
    status: str = "running"
    reason: str = ""
    problems_before: list[str] = Field(default_factory=list)
    problems_after: list[str] = Field(default_factory=list)
    steps: list[dict] = Field(default_factory=list)
    proposal: dict | None = None
    writes: int = 0
    fixes_applied: int = 0  # writes that passed verification (rolled-back writes do not count)
    rollbacks: int = 0
    retrieved_ids: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_s: float = 0.0
    trace_id: str | None = None


def _norm(s: str) -> str:
    return " ".join(s.split()).lower()


class Agent:
    def __init__(self, retriever: Retriever, llm: LLM, policy: Policy, runner: Runner, *,
                 settings: Settings | None = None, audit: AuditLog | None = None, telemetry: Telemetry | None = None,
                 kube_context: str | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.retriever, self.llm, self.policy, self.runner = retriever, llm, policy, runner
        self.s = settings or get_settings()
        self.audit = audit or AuditLog(None)
        self.tel = telemetry or get_telemetry()
        self.kube_context = kube_context
        self.sleep, self.clock = sleep, clock
        self.executor = Executor(runner)

    # ------------------------------------------------------------------ public
    def run(self, namespace: str, incident: str) -> AgentReport:
        rep = AgentReport(run_id=uuid.uuid4().hex[:12], environment=self.policy.environment, mode=self.policy.mode,
                          namespace=namespace, incident=redact(incident)[: self.s.max_question_chars])
        t0 = self.clock()
        with self.tel.span("agent.run", environment=self.policy.environment, mode=self.policy.mode, namespace=namespace):
            self.audit.write(rep.run_id, "run_start", environment=rep.environment, mode=rep.mode, namespace=namespace,
                             kube_context=self.kube_context or "")
            try:
                self._run(rep)
            except Exception as e:  # never let an unexpected error leave the run in an ambiguous state
                rep.status, rep.reason = "error", f"{type(e).__name__}: {e}"[:300]
            if rep.status == "running":
                rep.status = "not_resolved"
            if rep.fixes_applied and rep.status in ("denied", "escalated", "not_resolved"):
                rep.reason = f"{rep.status}: {rep.reason}".strip(": ")
                rep.status = "partially_resolved"  # at least one verified fix, but something is still unhealthy
            rep.duration_s = round(self.clock() - t0, 2)
            rep.trace_id = self.tel.current_trace_id()
            self.audit.write(rep.run_id, "run_end", status=rep.status, reason=rep.reason, writes=rep.writes,
                             rollbacks=rep.rollbacks, trace_id=rep.trace_id or "")
        self.tel.record_agent(rep)
        return rep

    # ------------------------------------------------------------------ internals
    def _step(self, rep: AgentReport, kind: str, **detail: Any) -> None:
        rep.steps.append({"kind": kind, **detail})
        self.audit.write(rep.run_id, kind, **detail)

    def _stop(self, rep: AgentReport, status: str, reason: str) -> None:
        rep.status, rep.reason = status, reason
        self._step(rep, "stop", status=status, reason=reason)

    def _run(self, rep: AgentReport) -> None:
        ns, pol = rep.namespace, self.policy
        d = pol.check_kube_context(self.kube_context)
        if not d.allowed:
            return self._stop(rep, "denied", d.reason)

        nsr = read(self.runner, ["get", "namespace", ns, "-o", "json"])
        if not nsr.ok:
            return self._stop(rep, "error", f"cannot read namespace '{ns}': {nsr.text[:150]}")
        import json

        labels = (json.loads(nsr.stdout).get("metadata") or {}).get("labels") or {}
        d = pol.check_namespace(ns, labels)
        if not d.allowed:
            return self._stop(rep, "denied", d.reason)

        state = collect_state(self.runner, ns)
        problems = find_problems(state)
        rep.problems_before = [p.line() for p in problems]
        if not problems:
            return self._stop(rep, "no_problem", "no unhealthy pods, deployments or services detected")

        query = rep.incident + " " + " ".join(f"{p.kind} {p.detail[:80]}" for p in problems[:3])
        hits = self.retriever.search(query, k=self.s.top_k)
        rep.retrieved_ids = [h.chunk.chunk_id for h in hits]
        gate = evaluate_gate(query, hits, self.s)
        self._step(rep, "retrieve", gate_ok=gate.ok, top_bm25=round(gate.top_bm25, 1), coverage=round(gate.coverage, 2))
        if not gate.ok:
            return self._stop(rep, "escalated", f"insufficient documentation evidence to act ({gate.reason})")

        observation = observe(self.runner, ns, problems)
        tried: list[str] = []  # human-readable, shown to the planner
        tried_keys: set[str] = set()  # exact actions already applied and rolled back
        deletes = 0
        for i in range(pol.max_steps):
            plan = self._plan(rep, ns, hits, observation, tried)
            if plan is None:
                return self._stop(rep, "error", "the model's plan could not be validated")
            self._step(rep, "plan", index=i, fixable=plan.fixable, rationale=plan.rationale,
                       action=plan.action.model_dump() if plan.action else None, citations=plan.citations,
                       evidence_quote=plan.evidence_quote)
            if not plan.fixable:
                return self._stop(rep, "escalated", plan.rationale or "not fixable automatically")
            action = plan.action
            if action is None:  # unreachable (PlanAction validates it) but never rely on assert for control flow
                return self._stop(rep, "error", "plan marked fixable without an action")
            key = action.model_dump_json()
            if key in tried_keys:
                return self._stop(rep, "denied", "repeated an action that was already tried and rolled back")
            bad = self._grounding_error(plan, hits, observation)
            if bad:
                return self._stop(rep, "denied", f"ungrounded proposal: {bad}")
            if action.namespace != ns:
                return self._stop(rep, "denied", f"action targets namespace '{action.namespace}', not '{ns}'")

            kind, name = target_ref(action)
            tr = read(self.runner, ["get", kind, name, "-n", ns, "-o", "json"])
            target = json.loads(tr.stdout) if tr.ok else None
            if target is None:
                return self._stop(rep, "denied", f"target {kind}/{name} not found")
            decision = pol.check_action(action, Context(rep.writes, deletes, target, state.pod_labels()))
            rollback_cmds = plan_rollback(action, target)
            self._step(rep, "policy", outcome=decision.outcome, reason=decision.reason, action=action.type)

            if decision.outcome != "allow":
                rep.proposal = {"action": action.model_dump(), "command": " ".join(["kubectl", *build_argv(action)]),
                                "rollback": [" ".join(["kubectl", *c]) for c in rollback_cmds],
                                "expected_outcome": plan.expected_outcome, "citations": plan.citations,
                                "evidence_quote": plan.evidence_quote, "rationale": plan.rationale}
                status = {"advise": "advised", "needs_approval": "needs_approval"}.get(decision.outcome, "denied")
                return self._stop(rep, status, decision.reason)

            res = self._apply(rep, action, decision, key)
            if res is not None:
                return self._stop(rep, "error", res)
            rep.writes += 1
            deletes += action.type == "delete_pod"

            ok, state, problems = self._verify(rep, action, target, problems)
            if ok:
                rep.fixes_applied += 1
                rep.problems_after = [p.line() for p in problems]
                if not problems:
                    return self._stop(rep, "resolved", f"{action.type} on {name} fixed the problem")
                observation = observe(self.runner, ns, problems)  # other workloads still unhealthy: plan the next fix
                continue
            # the change did not fix its target: undo it and let the planner try something else
            self._step(rep, "verify_failed", action=action.type, remaining=[p.line() for p in problems][:5])
            if pol.verification.get("rollback_on_failure", True) and rollback_cmds:
                results = self.executor.rollback(rollback_cmds)
                rep.rollbacks += 1
                self._step(rep, "rollback", ok=all(r.ok for r in results), commands=[" ".join(r.args[:3]) for r in results])
                self.sleep(pol.verification["settle_seconds"])
                state = collect_state(self.runner, ns)
                problems = find_problems(state)
            tried.append(f"{action.type} {key}")
            tried_keys.add(key)
            observation = observe(self.runner, ns, problems)
        rep.problems_after = [p.line() for p in find_problems(collect_state(self.runner, ns))]

    # ------------------------------------------------------------------ steps
    def _plan(self, rep: AgentReport, ns: str, hits, observation: str, tried: list[str]) -> PlanAction | None:
        msgs = build_messages(self.policy, ns, redact(rep.incident), hits, observation, tried, self.s.max_context_chars)
        plan, _attempts, err, usage = generate_model(self.llm, msgs, PlanAction)
        rep.prompt_tokens += usage["prompt_tokens"]
        rep.completion_tokens += usage["completion_tokens"]
        if plan is None:
            self._step(rep, "plan_invalid", error=err or "")
        return plan

    def _grounding_error(self, plan: PlanAction, hits, observation: str) -> str | None:
        retrieved = {h.chunk.chunk_id for h in hits}
        if not any(c in retrieved for c in plan.citations):
            return "no citation to a retrieved documentation chunk"
        quote = _norm(plan.evidence_quote)
        if len(quote) < 12 or quote not in _norm(observation):
            return "evidence_quote is not a verbatim quote of the live observation"
        return None

    def _apply(self, rep: AgentReport, action: Any, decision: Decision, key: str) -> str | None:
        dry = self.executor.dry_run(action, decision)
        if dry is not None and not dry.ok:
            self._step(rep, "dry_run_failed", action=action.type, error=dry.text[:300])
            return f"server-side dry-run rejected the change: {dry.text[:200]}"
        res = self.executor.apply(action, decision)
        self._step(rep, "apply", action=action.type, command=" ".join(res.args[:4]), ok=res.ok, output=res.text[:300])
        return None if res.ok else f"kubectl failed: {res.text[:200]}"

    def _verify(self, rep: AgentReport, action: Any, target: dict, before: list[Problem]
                ) -> tuple[bool, State, list[Problem]]:
        """Poll until the target workload is healthy and nothing new broke, or the timeout expires."""
        v = self.policy.verification
        _, name = target_ref(action)
        workload = name if action.type != "delete_pod" else next(
            (p.workload for p in before if p.name == name), name)
        old_keys = {p.key() for p in before}
        self.sleep(v["settle_seconds"])
        deadline = self.clock() + v["timeout_seconds"]
        while True:
            state = collect_state(self.runner, rep.namespace)
            problems = find_problems(state)
            target_ok = not any(p.workload == workload for p in problems)
            new = [p for p in problems if p.key() not in old_keys]
            if target_ok and not new:
                self._step(rep, "verify", ok=True, workload=workload, remaining=len(problems))
                return True, state, problems
            if self.clock() >= deadline:
                self._step(rep, "verify", ok=False, workload=workload, new_problems=[p.line() for p in new][:3])
                return False, state, problems
            self.sleep(v["poll_seconds"])
