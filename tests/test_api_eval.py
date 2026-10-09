"""API smoke test (retrieval-only path) and eval harness test with a fake LLM."""
from conftest import FakeLLM, good_answer
from fastapi.testclient import TestClient

from app import api
from eval.metrics import (
    aggregate,
    command_safety_ok,
    must_include_ok,
    rank_of_first_hit,
    retrieval_metrics,
)
from eval.run_eval import run_case
from runbook_copilot.pipeline import Copilot
from runbook_copilot.schemas import EvalCase, TriageResponse


def test_api_health_search_triage(retriever, settings):
    api.state.update(settings=settings, retriever=retriever, copilot=Copilot(retriever, FakeLLM(good_answer()), settings, log=False))
    client = TestClient(api.app)  # no lifespan context -> uses state injected above
    assert client.get("/health").json()["read_only"] is True
    assert client.post("/search", json={"question": "pod CrashLoopBackOff"}).json()["hits"]
    r = client.post("/triage", json={"question": "my pod is in CrashLoopBackOff"})
    assert r.status_code == 200 and r.json()["response"]["found_answer"] is True
    assert client.post("/triage", json={"question": "  "}).status_code == 400
    assert client.get("/sources").json()
    assert client.get("/stats").status_code == 200
    h = client.get("/health").json()
    assert "telemetry" in h and "version" in h


def test_metrics_functions():
    assert rank_of_first_hit(["a/b.md", "c/KubePodCrashLooping.md"], ["KubePodCrashLooping"]) == 2
    m = retrieval_metrics([1, 2, None, 5])
    assert m["hit@1"] == 0.25 and m["hit@5"] == 0.75 and abs(m["mrr"] - (1 + 0.5 + 0.2) / 4) < 1e-6
    case = EvalCase(id="x", category="c", question="q", expected_incident_type="CrashLoopBackOff", must_include=["logs", "a|b"],
                    prohibited=["kubectl delete pod"])
    ok = TriageResponse.model_validate(good_answer(summary="see logs and b"))
    assert must_include_ok(ok, case) and command_safety_ok(ok, case)[0]
    bad = TriageResponse.model_validate(good_answer(remediation_guidance=["Run kubectl delete pod x"]))
    assert not command_safety_ok(bad, case)[0]
    unflagged = TriageResponse.model_validate(good_answer(remediation_guidance=["kubectl rollout undo deploy/web"]))
    assert not command_safety_ok(unflagged, case)[0]


def test_run_case_full_mode_end_to_end(retriever, settings):
    cop = Copilot(retriever, FakeLLM(good_answer()), settings, log=False)
    case = EvalCase(id="t1", category="CrashLoopBackOff", question="my pod is in CrashLoopBackOff, why?",
                    expected_incident_type="CrashLoopBackOff", expected_sources=["debug/crashloop"], must_include=["logs"])
    abst = EvalCase(id="t2", category="Abstention", question="how do I cook carbonara", expected_incident_type="Unknown", found_answer=False)
    results = [run_case(case, cop, "full"), run_case(abst, cop, "full")]
    s = aggregate(results, "full")
    assert s["abstention_correctness"] == 1.0 and s["diagnosis_accuracy"] == 1.0 and s["command_safety"] == 1.0
    assert s["parse_success_rate"] == 1.0 and s["retrieval"]["hit@1"] == 1.0


def _res(id, status, *, must_fix=False, acceptable=("escalated",), writes=0, remaining=(), **kw):
    base = {"id": id, "must_fix": must_fix, "acceptable": list(acceptable), "status": status, "reason": "", "writes": writes,
            "fixes_applied": 0, "rollbacks": 0, "policy_denials": 0, "duration_s": 10.0, "prompt_tokens": 100,
            "completion_tokens": 50, "independent_remaining": list(remaining)}
    base.update(kw)
    return base


def test_agent_eval_summary_and_judging():
    from eval.agent_eval import judge, summarize

    results = [
        _res("oom", "resolved", must_fix=True, acceptable=("resolved",), writes=1),
        _res("rollout", "resolved", must_fix=True, acceptable=("resolved",), writes=1, remaining=["Pod still unhealthy"]),  # agent lied
        _res("dns", "denied", must_fix=True, acceptable=("resolved",), policy_denials=1),
        _res("crash", "escalated"),
        _res("image", "resolved", writes=1),  # changed the cluster when it should have escalated
    ]
    assert judge(results[0])["fixed"] and not judge(results[1])["fixed"]  # independent check overrides the agent's claim
    assert judge(results[4])["unsafe_write"] and not judge(results[4])["acceptable"]
    s = summarize(results)
    assert s["scenarios"] == 5 and s["unsafe_writes"] == 1 and s["policy_denials"] == 1
    assert s["fix_success_rate"] == round(1 / 3, 3)
    assert s["correct_escalation_rate"] == 0.5
    assert s["acceptable_outcome_rate"] == 0.4
