import json

import pytest

from runbook_copilot.config import Settings
from runbook_copilot.pipeline import Copilot
from runbook_copilot.retrieval.search import Retriever
from runbook_copilot.schemas import Chunk


def make_chunk(cid, title, heading, text, tags=None):
    return Chunk(chunk_id=cid, source_id=cid.split(":")[0], doc_path=cid.split(":")[1].split("#")[0] + ".md",
                 url=f"https://example.test/{cid}", title=title, heading_path=heading, text=text,
                 license="CC-BY-4.0", commit_sha="abc123", tags=tags or [])


@pytest.fixture
def chunks():
    return [
        make_chunk("k8s-docs:debug/crashloop#00", "Debug CrashLoopBackOff", "Debug > CrashLoopBackOff",
                   "A pod in CrashLoopBackOff keeps restarting because its container exits. Check the previous container "
                   "logs with kubectl logs <pod-name> --previous and inspect events with kubectl describe pod <pod-name>. "
                   "Common causes are application errors, bad configuration, and failing liveness probes."),
        make_chunk("k8s-docs:debug/imagepull#00", "Images", "Images > ImagePullBackOff",
                   "ImagePullBackOff means the kubelet cannot pull the container image. Typical causes are a wrong image "
                   "name or tag, or missing imagePullSecrets for a private registry. Use kubectl describe pod to see events."),
        make_chunk("k8s-docs:sched/pending#00", "Scheduling", "Scheduling > Pending pods",
                   "A pod stays Pending when the scheduler cannot place it, for example insufficient CPU or memory, "
                   "untolerated taints or node selectors that match no node. kubectl describe pod shows FailedScheduling."),
        make_chunk("k8s-docs:misc/other#00", "Cooking", "Cooking > Recipes", "Pasta needs salted water and ten minutes."),
    ]


@pytest.fixture
def settings(tmp_path):
    return Settings(log_path=tmp_path / "req.jsonl", min_bm25_score=0.5, min_query_coverage=0.3, llm_api_key="x")


@pytest.fixture
def retriever(chunks):
    return Retriever(chunks)


class FakeLLM:
    """Returns queued responses (str or dict) in order; records calls."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, messages):
        self.calls += 1
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return r if isinstance(r, str) else json.dumps(r)


def good_answer(**over):
    base = {
        "found_answer": True, "incident_type": "CrashLoopBackOff",
        "summary": "The container keeps exiting and the kubelet restarts it.",
        "likely_causes": ["Application error", "Failing liveness probe"],
        "evidence": ["A pod in CrashLoopBackOff keeps restarting because its container exits"],
        "diagnostic_commands": ["kubectl logs <pod-name> --previous", "kubectl describe pod <pod-name>"],
        "remediation_guidance": ["Fix the application error shown in the previous logs."],
        "confidence": 0.85, "citations": ["k8s-docs:debug/crashloop#00"], "answer_not_found_reason": None,
    }
    base.update(over)
    return base


@pytest.fixture
def make_copilot(retriever, settings):
    def _make(llm):
        return Copilot(retriever, llm, settings, log=False)
    return _make
