"""Run the evaluation suite.

  python -m eval.run_eval --mode retrieval          # no LLM needed: retrieval quality + gate behaviour
  python -m eval.run_eval --mode full               # full pipeline, needs LLM credentials
  python -m eval.run_eval --mode full --ids cl-01 ab-01
  python -m eval.run_eval --mode retrieval --min-hit5 0.8     # non-zero exit if below (for CI)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

from eval.metrics import aggregate, command_safety_ok, must_include_ok, rank_of_first_hit
from runbook_copilot.config import get_settings
from runbook_copilot.llm.client import make_llm
from runbook_copilot.pipeline import Copilot
from runbook_copilot.retrieval.search import Retriever, evaluate_gate
from runbook_copilot.schemas import EvalCase

CASES_DIR = Path(__file__).parent / "cases"
REPORTS_DIR = Path(__file__).parent / "reports"


def load_cases(ids: list[str] | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        cases += [EvalCase(**c) for c in yaml.safe_load(f.read_text())]
    if ids:
        cases = [c for c in cases if c.id in ids]
    return cases


def run_case(case: EvalCase, copilot: Copilot, mode: str) -> dict:
    s = copilot.s
    hits = copilot.retriever.search(case.question, k=s.top_k)
    gate = evaluate_gate(case.question, hits, s)
    rank = rank_of_first_hit([h.chunk.doc_path for h in hits[:5]], case.expected_sources) if case.expected_sources else None
    rec = {"id": case.id, "category": case.category, "question": case.question, "expected_found": case.found_answer,
           "rank": rank, "gate_ok": gate.ok, "gate_reason": gate.reason, "top_bm25": round(gate.top_bm25, 1),
           "coverage": round(gate.coverage, 2), "top_ids": [h.chunk.chunk_id for h in hits[:5]]}
    if mode != "full":
        return rec

    res = copilot.triage(case.question)
    r, t = res.response, res.trace
    cited_paths = [cid.split(":", 1)[1].split("#")[0] for cid in r.citations]
    safe, problems = command_safety_ok(r, case)
    rec.update({
        "found": r.found_answer, "incident_type": r.incident_type, "confidence": r.confidence,
        "incident_ok": r.incident_type == case.expected_incident_type,
        "must_include_ok": must_include_ok(r, case) if r.found_answer else False,
        "citation_hit": any(e in p for p in cited_paths for e in case.expected_sources) if case.expected_sources else False,
        "groundedness": t.groundedness, "safe": safe, "safety_problems": problems,
        "guardrail_intervened": bool(t.dropped_commands or t.flagged_remediation or t.dropped_citations),
        "parse_ok": t.parse_ok, "latency_ms": t.latency_ms, "abstain_source": t.abstain_source,
        "answer": r.model_dump(),
    })
    return rec


def markdown_report(summary: dict, results: list[dict], mode: str) -> str:
    lines = [f"# Eval report ({mode})", "", f"_Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}, {summary['cases']} cases_", "",
             "## Summary", "", "```json", json.dumps(summary, indent=2), "```", "", "## Per-case", ""]
    if mode == "full":
        lines += ["| id | category | rank | found (exp) | type ok | must-include | safe | latency ms |", "|---|---|---|---|---|---|---|---|"]
        for r in results:
            lines.append(f"| {r['id']} | {r['category']} | {r['rank'] or '-'} | {r['found']} ({r['expected_found']}) | "
                         f"{r['incident_ok']} | {r['must_include_ok']} | {r['safe']} | {r['latency_ms']} |")
    else:
        lines += ["| id | category | first-hit rank | gate ok (expected answerable) | top BM25 | coverage |", "|---|---|---|---|---|---|"]
        for r in results:
            lines.append(f"| {r['id']} | {r['category']} | {r['rank'] or '-'} | {r['gate_ok']} ({r['expected_found']}) | {r['top_bm25']} | {r['coverage']} |")
    misses = [r for r in results if r["expected_found"] and r["rank"] is None]
    if misses:
        lines += ["", "## Retrieval misses (inspect these first)", ""]
        lines += [f"- **{r['id']}** {r['question']}  \n  top: {', '.join(r['top_ids'][:3])}" for r in misses]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--exclude-source", nargs="*", default=[], help="ablation: drop these source ids from the index, e.g. lab-runbooks")
    ap.add_argument("--min-hit5", type=float)
    ap.add_argument("--min-abstention", type=float)
    ap.add_argument("--min-safety", type=float)
    args = ap.parse_args()

    s = get_settings()
    cases = load_cases(args.ids)
    llm = make_llm(s) if args.mode == "full" else None
    retriever = Retriever.load(s)
    if args.exclude_source:  # ablation: rebuild the index without some sources
        retriever = Retriever([c for c in retriever.chunks if c.source_id not in args.exclude_source])
        print(f"ablation: excluded {args.exclude_source}, {len(retriever.chunks)} chunks remain", file=sys.stderr)
    copilot = Copilot(retriever, llm, s, log=False)

    results = []
    for c in cases:
        results.append(run_case(c, copilot, args.mode))
        print(f"  {c.id:6} done", file=sys.stderr)
    summary = aggregate(results, args.mode)

    REPORTS_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    (REPORTS_DIR / f"{stamp}_{args.mode}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    md = markdown_report(summary, results, args.mode)
    (REPORTS_DIR / f"latest_{args.mode}.md").write_text(md)
    print(json.dumps(summary, indent=2))

    failed = []
    if args.min_hit5 is not None and summary["retrieval"].get("hit@5", 0) < args.min_hit5:
        failed.append("hit@5")
    if args.min_abstention is not None and summary.get("abstention_correctness", 1) < args.min_abstention:
        failed.append("abstention")
    if args.min_safety is not None and summary.get("command_safety", 1) < args.min_safety:
        failed.append("command_safety")
    if failed:
        print(f"FAILED thresholds: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
