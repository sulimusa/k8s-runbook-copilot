from runbook_copilot.retrieval.search import evaluate_gate
from runbook_copilot.retrieval.text import tokenize


def test_tokenizer_splits_camel_case_and_plurals():
    t = tokenize("CrashLoopBackOff pods")
    assert "crashloopbackoff" in t and "crash" in t and "loop" in t and "pod" in t
    assert "kubernetes" in tokenize("Kubernetes")  # not stemmed to 'kubernete'


def test_retrieves_right_chunk(retriever):
    hits = retriever.search("pod keeps crash looping, container restarts", k=3)
    assert hits[0].chunk.chunk_id == "k8s-docs:debug/crashloop#00"


def test_retrieves_pending(retriever):
    hits = retriever.search("pod Pending FailedScheduling insufficient cpu", k=3)
    assert hits[0].chunk.chunk_id == "k8s-docs:sched/pending#00"


def test_gate_passes_good_and_blocks_out_of_scope(retriever, settings):
    q = "pod in CrashLoopBackOff"
    assert evaluate_gate(q, retriever.search(q), settings).ok
    q2 = "how do I make carbonara pasta"
    g = evaluate_gate(q2, retriever.search(q2), settings)
    assert not g.ok and "out_of_scope" in g.reason
