"""FastAPI service.   uvicorn app.api:app --reload --port 8000

POST /triage   {"question": "..."}  -> TriageResult (response + trace + sources)
POST /search   {"question": "..."}  -> retrieval only (works without an LLM key)
GET  /health   GET /stats (log summary)   GET /sources
Telemetry: OTLP traces + metrics when OTEL_ENABLED=true (see docs/observability.md)
"""
from __future__ import annotations

import json
import os
import secrets
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from runbook_copilot.atlas_monitoring import dashboard, summary
from runbook_copilot.atlas_runtime import configured_model, save_report
from runbook_copilot.config import ROOT, get_settings
from runbook_copilot.investigation import MODES, Step, investigate, load_fixture, render_report
from runbook_copilot.llm.client import LLMNotConfigured, make_llm
from runbook_copilot.observability import load_and_summarize
from runbook_copilot.pipeline import Copilot
from runbook_copilot.retrieval.search import Retriever, evaluate_gate
from runbook_copilot.schemas import TriageRequest, TriageResult
from runbook_copilot.telemetry import get_telemetry, instrument_fastapi, setup_telemetry

state: dict = {'atlas_token': secrets.token_urlsafe(32)}


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


@app.get('/demo/rollout-oom', response_class=HTMLResponse)
def rollout_demo_index():
    return ('<html lang="en"><meta charset="utf-8"><title>Atlas rollout demo</title>'
            '<h1>Atlas rollout/OOM investigation</h1>'
            '<p>Synthetic observation replay. Offline links use a disclosed rule-based planner. '
            'The separate model button makes bounded API calls only when enabled locally. No cluster actions.</p>'
            '<p><a href="/atlas/monitoring">Investigation monitoring and saved reports</a></p>'
            '<p>Each run searches the indexed corpus; expand the steps to inspect decisions, observations and sources.</p>'
            + ''.join(f'<h2>{case}</h2><ul>' + ''.join(
                f'<li><a href="/demo/rollout-oom/{case}?mode={mode}">{mode}</a></li>' for mode in MODES)
                + '</ul><button onclick="runModel(\'' + case + '\')">Run real LLM investigation</button>'
                for case in ('routing', 'buffer', 'incomplete'))
            + '<p id="progress"></p><script>async function runModel(c){'
            'document.querySelectorAll("button").forEach(b=>b.disabled=true);'
            'document.getElementById("progress").textContent="Investigating; this can take a minute…";'
            'try{const r=await fetch("/atlas/investigate/"+c,{method:"POST",headers:{"X-Atlas-Token":'
            + json.dumps(state['atlas_token']) + '}});const d=await r.json();'
            'if(!r.ok)throw new Error(d.detail);location.href="/atlas/runs/"+d.run_id;'
            '}catch(e){document.getElementById("progress").textContent=e.message;'
            'document.querySelectorAll("button").forEach(b=>b.disabled=false);}}</script></html>')


@app.post('/atlas/investigate/{case}')
def atlas_model_run(case: str, request: Request):
    if not secrets.compare_digest(request.headers.get('x-atlas-token', ''), state['atlas_token']):
        raise HTTPException(403, 'Open the local demo page to start a model run')
    if os.environ.get('ATLAS_MODEL_RUNS_ENABLED') != 'true':
        raise HTTPException(503, 'Model runs are disabled; configure the local model key and budget first')
    if case not in ('routing', 'buffer', 'incomplete'):
        raise HTTPException(400, 'Unknown replay case')
    try:
        model = configured_model(Step)
    except (ValueError, LLMNotConfigured):
        raise HTTPException(503, 'Configure a valid local API key, verified prices and campaign budget')
    report = investigate(load_fixture(case), state['retriever'], llm=model)
    report['case'] = case
    save_report(report)
    return {'run_id': report['run_id'], 'status': report['status']}


@app.get('/atlas/runs/{run_id}', response_class=HTMLResponse)
def atlas_report(run_id: UUID):
    path = ROOT / 'logs/atlas-runs' / (str(run_id) + '.json')
    if not path.exists():
        raise HTTPException(404, 'No saved investigation')
    return render_report(json.loads(path.read_text()))


@app.get('/atlas/monitoring', response_class=HTMLResponse)
def atlas_dashboard():
    return dashboard()


@app.get('/atlas/stats')
def atlas_stats():
    return summary()


@app.get('/demo/rollout-oom/{case}', response_class=HTMLResponse)
def rollout_demo(case: str, mode: str = 'rag'):
    if mode not in MODES or case not in ('routing', 'buffer', 'incomplete'):
        raise HTTPException(400, 'Unknown replay case or mode')
    report = investigate(load_fixture(case), state['retriever'], mode=mode)
    return render_report(report)


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
