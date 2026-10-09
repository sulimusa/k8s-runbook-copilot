import json

import pytest
from conftest import FakeLLM, good_answer
from pydantic import ValidationError

from runbook_copilot.llm.client import LLMNotConfigured
from runbook_copilot.schemas import TriageResponse

Q = "my pod is in CrashLoopBackOff, what do I check?"


def test_happy_path_and_unsafe_command_dropped(make_copilot):
    ans = good_answer(diagnostic_commands=["kubectl logs <pod-name> --previous", "kubectl delete pod <pod-name>"],
                      remediation_guidance=["kubectl rollout undo deployment/web", "kubectl delete pod --all --force"])
    r = make_copilot(FakeLLM(ans)).triage(Q)
    assert r.response.found_answer and r.response.citations == ["k8s-docs:debug/crashloop#00"]
    assert r.response.diagnostic_commands == ["kubectl logs <pod-name> --previous"]
    assert r.trace.dropped_commands == ["kubectl delete pod <pod-name>"]
    assert r.response.remediation_guidance[0].startswith("[Manual change")
    assert len(r.response.remediation_guidance) == 1  # --force / --all advice removed
    assert r.trace.latency_ms > 0 and r.trace.parse_ok and r.sources[0]["url"].startswith("https://")


def test_gate_abstains_without_calling_llm(make_copilot):
    llm = FakeLLM(good_answer())
    r = make_copilot(llm).triage("how do I make carbonara pasta")
    assert not r.response.found_answer and r.trace.abstain_source == "gate" and llm.calls == 0


def test_retry_on_invalid_json_then_success(make_copilot):
    llm = FakeLLM("not json at all", good_answer())
    r = make_copilot(llm).triage(Q)
    assert r.response.found_answer and r.trace.parse_attempts == 2 and r.trace.parse_ok


def test_parse_failure_abstains(make_copilot):
    r = make_copilot(FakeLLM("garbage")).triage(Q)
    assert not r.response.found_answer and not r.trace.parse_ok and r.trace.abstain_source == "parse_failure"


def test_code_fenced_json_is_accepted(make_copilot):
    r = make_copilot(FakeLLM("```json\n" + json.dumps(good_answer()) + "\n```")).triage(Q)
    assert r.response.found_answer and r.trace.parse_attempts == 1


def test_hallucinated_citation_is_dropped_and_abstains(make_copilot):
    r = make_copilot(FakeLLM(good_answer(citations=["k8s-docs:made/up#99"]))).triage(Q)
    assert not r.response.found_answer and r.trace.abstain_source == "no_valid_citations"
    assert r.trace.dropped_citations == ["k8s-docs:made/up#99"]


def test_llm_abstention_is_respected(make_copilot):
    ans = {"found_answer": False, "incident_type": "Unknown", "summary": "n/a", "confidence": 0.0,
           "answer_not_found_reason": "context does not cover this"}
    r = make_copilot(FakeLLM(ans)).triage(Q)
    assert not r.response.found_answer and r.trace.abstain_source == "llm"


def test_ungrounded_evidence_lowers_confidence(make_copilot):
    r = make_copilot(FakeLLM(good_answer(evidence=["Istio sidecar mesh policy misconfigured upstream"], confidence=0.9))).triage(Q)
    # groundedness 0 -> cap 0.2 < min_confidence 0.35 -> abstain
    assert not r.response.found_answer and r.trace.abstain_source == "low_confidence"


def test_unknown_incident_type_normalised(make_copilot):
    r = make_copilot(FakeLLM(good_answer(incident_type="crashloopbackoff"))).triage(Q)
    assert r.response.incident_type == "CrashLoopBackOff"


def test_no_llm_configured_raises_only_when_needed(make_copilot):
    with pytest.raises(LLMNotConfigured):
        make_copilot(None).triage(Q)
    assert not make_copilot(None).triage("make pasta").response.found_answer  # gate path needs no LLM


def test_empty_question_rejected(make_copilot):
    with pytest.raises(ValueError):
        make_copilot(FakeLLM(good_answer())).triage("   ")


def test_schema_validator():
    with pytest.raises(ValidationError):
        TriageResponse(found_answer=True, incident_type="x", summary="s", confidence=0.5)  # no citations
    with pytest.raises(ValidationError):
        TriageResponse(found_answer=False, incident_type="x", summary="s", confidence=0.0)  # no reason
    with pytest.raises(ValidationError):
        TriageResponse(found_answer=False, incident_type="x", summary="s", confidence=1.5, answer_not_found_reason="r")
