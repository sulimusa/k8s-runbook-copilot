"""Minimal observability: one JSON line per request + a summary used by /metrics and the UI.
Tracks latency, parse failures, abstentions and retrieval quality signals (top BM25, coverage)."""
from __future__ import annotations

import hashlib
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import Settings, get_settings
from .schemas import Trace


@contextmanager
def timer():
    t = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield t
    finally:
        t["ms"] = (time.perf_counter() - start) * 1000


def log_request(question: str, trace: Trace, found_answer: bool, incident_type: str, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    s.log_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "q_hash": hashlib.sha256(question.encode()).hexdigest()[:12],
        "found_answer": found_answer,
        "incident_type": incident_type,
        **trace.model_dump(),
    }
    if s.log_questions:
        rec["question"] = question[:300]
    with s.log_path.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    return vals[min(len(vals) - 1, round(p * (len(vals) - 1)))]


def summarize(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"requests": 0}
    lat = [r["latency_ms"] for r in records]
    return {
        "requests": n,
        "latency_ms_p50": round(_pct(lat, 0.5), 1),
        "latency_ms_p95": round(_pct(lat, 0.95), 1),
        "parse_failure_rate": round(sum(1 for r in records if not r["parse_ok"]) / n, 4),
        "abstain_rate": round(sum(1 for r in records if not r["found_answer"]) / n, 4),
        "gate_abstain_rate": round(sum(1 for r in records if r.get("abstain_source") == "gate") / n, 4),
        "mean_top_bm25": round(sum(r["top_bm25"] for r in records) / n, 2),
        "mean_query_coverage": round(sum(r["query_coverage"] for r in records) / n, 3),
        "dropped_commands_total": sum(len(r.get("dropped_commands", [])) for r in records),
        "dropped_citations_total": sum(len(r.get("dropped_citations", [])) for r in records),
    }


def load_and_summarize(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    if not s.log_path.exists():
        return {"requests": 0}
    records = [json.loads(ln) for ln in s.log_path.read_text().splitlines() if ln.strip()]
    return summarize(records)
