"""Streamlit demo.   streamlit run app/ui.py"""
import streamlit as st

from runbook_copilot.config import get_settings
from runbook_copilot.llm.client import LLMNotConfigured, make_llm
from runbook_copilot.observability import load_and_summarize
from runbook_copilot.pipeline import Copilot
from runbook_copilot.retrieval.search import Retriever, evaluate_gate

st.set_page_config(page_title="Kubernetes Runbook Copilot", page_icon="☸️", layout="wide")

EXAMPLES = [
    "My pod is in CrashLoopBackOff. How do I find out why it keeps restarting?",
    "Pod is Pending with FailedScheduling: 0/3 nodes are available: Insufficient cpu.",
    "My Service has no endpoints and requests to it time out.",
    "Deployment condition shows ProgressDeadlineExceeded. What does it mean?",
    "How do I configure AWS IAM roles for EKS service accounts?",
]


@st.cache_resource
def load():
    s = get_settings()
    retriever = Retriever.load(s)
    try:
        llm = make_llm(s)
    except LLMNotConfigured:
        llm = None
    return s, retriever, Copilot(retriever, llm, s)


s, retriever, copilot = load()

st.title("☸️ Kubernetes Runbook Copilot")
st.caption("Read-only incident triage grounded in public Kubernetes docs, community runbooks and lab evidence. "
           "It recommends commands; it never executes anything.")

with st.sidebar:
    st.header("Status")
    st.write(f"Chunks indexed: **{len(retriever.chunks)}**")
    st.write(f"LLM: **{'configured (' + s.llm_model + ')' if copilot.llm else 'not configured (retrieval-only)'}**")
    st.write(f"Hybrid retrieval: **{'on' if retriever.embeddings is not None else 'off (BM25)'}**")
    st.divider()
    st.subheader("Live metrics")
    st.json(load_and_summarize(s))
    st.divider()
    ex = st.selectbox("Examples", [""] + EXAMPLES)

q = st.text_area("Describe the problem (paste error messages, pod status or events):", value=ex, height=120)

if st.button("Triage", type="primary") and q.strip():
    if copilot.llm is None:
        hits = retriever.search(q, k=s.top_k)
        gate = evaluate_gate(q, hits, s)
        st.warning("No LLM key configured: showing retrieval results only.")
        st.write(f"Gate: {'pass' if gate.ok else 'abstain'} (top BM25 {gate.top_bm25:.1f}, coverage {gate.coverage:.2f}) {gate.reason or ''}")
        for h in hits:
            with st.expander(f"{h.chunk.heading_path}  ·  BM25 {h.bm25:.1f}"):
                st.markdown(f"[{h.chunk.url}]({h.chunk.url})")
                st.markdown(h.chunk.text)
    else:
        with st.spinner("Retrieving evidence and generating a cited answer..."):
            result = copilot.triage(q)
        r, t = result.response, result.trace
        if not r.found_answer:
            st.error("Insufficient evidence")
            st.write(r.answer_not_found_reason)
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Incident type", r.incident_type)
            c2.metric("Confidence", f"{r.confidence:.0%}")
            c3.metric("Latency", f"{t.latency_ms / 1000:.1f}s")
            st.subheader("Diagnosis")
            st.write(r.summary)
            left, right = st.columns(2)
            with left:
                st.subheader("Likely causes")
                for x in r.likely_causes:
                    st.markdown(f"- {x}")
                st.subheader("Evidence")
                for x in r.evidence:
                    st.markdown(f"> {x}")
            with right:
                st.subheader("Safe diagnostic commands (read-only)")
                for cmd in r.diagnostic_commands:
                    st.code(cmd, language="bash")
                st.subheader("Remediation guidance (manual, review first)")
                for x in r.remediation_guidance:
                    st.markdown(f"- {x}")
        st.subheader("Sources")
        for src in result.sources:
            st.markdown(f"- [{src['title']}]({src['url']}) · `{src['chunk_id']}` · {src['license']}")
        with st.expander("Trace"):
            st.json(t.model_dump())
