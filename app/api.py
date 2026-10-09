"""FastAPI service.   uvicorn app.api:app --reload --port 8000

POST /triage   {"question": "..."}  -> TriageResult (response + trace + sources)
POST /search   {"question": "..."}  -> retrieval only (works without an LLM key)
GET  /health   GET /stats (log summary)   GET /sources
Telemetry: OTLP traces + metrics when OTEL_ENABLED=true (see docs/observability.md)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from runbook_copilot.config import get_settings
from runbook_copilot.llm.client import LLMNotConfigured, make_llm
from runbook_copilot.observability import load_and_summarize
from runbook_copilot.pipeline import Copilot
from runbook_copilot.retrieval.search import Retriever, evaluate_gate
from runbook_copilot.schemas import TriageRequest, TriageResult
from runbook_copilot.telemetry import get_telemetry, instrument_fastapi, setup_telemetry

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    state["settings"] = s
    tel = setup_telemetry(s)
    instrument_fastapi(app)
    state["retriever"] = Retriever.load(s)
    try:
        llm = make_llm(s)
    except LLMNotConfigured:
        llm = None
    state["copilot"] = Copilot(state["retriever"], llm, s, telemetry=tel)
    yield


app = FastAPI(title="Kubernetes Runbook Copilot", version="0.1.0", lifespan=lifespan,
              description="Read-only, source-cited Kubernetes incident triage. It never executes commands.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health")
def health():
    c = state["copilot"]
    return {"status": "ok", "chunks": len(state["retriever"].chunks), "llm_configured": c.llm is not None,
            "hybrid_retrieval": state["retriever"].embeddings is not None, "read_only": True,
            "environment": state["settings"].app_env, "version": state["settings"].app_version,
            "telemetry": get_telemetry().enabled}


@app.post("/triage", response_model=TriageResult)
def triage(req: TriageRequest):
    try:
        return state["copilot"].triage(req.question)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMNotConfigured as e:
        raise HTTPException(503, f"{e}. Use POST /search for retrieval-only mode.")


@app.post("/search")
def search(req: TriageRequest):
    s = state["settings"]
    hits = state["retriever"].search(req.question, k=s.top_k)
    gate = evaluate_gate(req.question, hits, s)
    return {"gate": gate.__dict__,
            "hits": [{"chunk_id": h.chunk.chunk_id, "bm25": round(h.bm25, 2), "heading": h.chunk.heading_path,
                      "url": h.chunk.url, "snippet": h.chunk.text[:300]} for h in hits]}


@app.get("/stats")
def stats():
    return load_and_summarize(state["settings"])


@app.get("/sources")
def sources():
    seen: dict = {}
    for c in state["retriever"].chunks:
        d = seen.setdefault(c.source_id, {"source_id": c.source_id, "license": c.license, "commit": c.commit_sha, "chunks": 0})
        d["chunks"] += 1
    return list(seen.values())
