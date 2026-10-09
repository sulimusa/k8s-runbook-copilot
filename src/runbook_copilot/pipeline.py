"""question -> retrieve -> gate -> prompt -> LLM -> validate -> guardrails -> TriageResult"""
from __future__ import annotations

from .config import Settings, get_settings
from .llm.client import LLM, LLMNotConfigured, generate_triage
from .llm.prompts import build_messages
from .observability import log_request, timer
from .retrieval.search import Retriever, evaluate_gate
from .safety import check_citations, filter_commands, groundedness, sanitize_remediation
from .schemas import INCIDENT_TYPES, RetrievedChunk, Trace, TriageResponse, TriageResult
from .telemetry import Telemetry, get_telemetry


def abstain(reason: str, incident_type: str = "Unknown") -> TriageResponse:
    return TriageResponse(
        found_answer=False, incident_type=incident_type,
        summary="I don't have enough evidence in the indexed public sources to answer this reliably.",
        confidence=0.0, answer_not_found_reason=reason,
    )


def _normalize_incident_type(t: str) -> str:
    lookup = {x.lower(): x for x in INCIDENT_TYPES}
    return lookup.get(t.strip().lower(), "Unknown")


def _source_view(hits: list[RetrievedChunk], ids: list[str] | None = None) -> list[dict]:
    by_id = {h.chunk.chunk_id: h.chunk for h in hits}
    chosen = ids if ids is not None else list(by_id)
    return [{"chunk_id": i, "title": by_id[i].title, "section": by_id[i].heading_path, "url": by_id[i].url,
             "license": by_id[i].license} for i in chosen if i in by_id]


class Copilot:
    def __init__(self, retriever: Retriever, llm: LLM | None = None, settings: Settings | None = None,
                 log: bool = True, telemetry: Telemetry | None = None):
        self.retriever = retriever
        self.llm = llm
        self.s = settings or get_settings()
        self.log = log
        self.tel = telemetry or get_telemetry()

    def triage(self, question: str) -> TriageResult:
        question = (question or "").strip()
        if not question:
            raise ValueError("question must not be empty")
        question = question[: self.s.max_question_chars]
        trace = Trace()
        with self.tel.span("copilot.triage", question_chars=len(question), environment=self.s.app_env,
                           version=self.s.app_version) as root:
            with timer() as total:
                result = self._run(question, trace)
            trace.latency_ms = round(total["ms"], 1)  # timer value is only final after the block exits
            trace.trace_id = self.tel.current_trace_id()
            r = result.response
            root.set(found_answer=r.found_answer, incident_type=r.incident_type, abstain_source=trace.abstain_source,
                     confidence=r.confidence, top_bm25=trace.top_bm25, parse_attempts=trace.parse_attempts,
                     prompt_tokens=trace.prompt_tokens, completion_tokens=trace.completion_tokens)
        self.tel.record_request(result)
        self._log(question, result)
        return result

    def _run(self, question: str, trace: Trace) -> TriageResult:
        with timer() as t_ret, self.tel.span("copilot.retrieve") as sp:
            hits = self.retriever.search(question, k=self.s.top_k)
            gate = evaluate_gate(question, hits, self.s)
            sp.set(hits=len(hits), top_bm25=gate.top_bm25, coverage=gate.coverage, gate_ok=gate.ok, gate_reason=gate.reason)
        trace.retrieval_ms = round(t_ret["ms"], 1)
        trace.top_bm25, trace.query_coverage = gate.top_bm25, gate.coverage
        trace.gate_ok, trace.gate_reason = gate.ok, gate.reason
        trace.retrieved_ids = [h.chunk.chunk_id for h in hits]

        if not gate.ok:
            trace.abstain_source = "gate"
            resp = abstain(f"Retrieved evidence was insufficient ({gate.reason}). "
                           "Try adding the exact error message, pod status, or event text.")
            return TriageResult(response=resp, trace=trace, sources=_source_view(hits[:3]))

        if self.llm is None:
            raise LLMNotConfigured("No LLM configured. Set LLM_API_KEY in .env")

        with timer() as t_llm, self.tel.span("copilot.llm.generate", model=self.s.llm_model) as sp:
            parsed, attempts, err, usage = generate_triage(self.llm, build_messages(question, hits, self.s.max_context_chars))
            sp.set(attempts=attempts, parse_ok=parsed is not None, **usage)
        trace.llm_ms, trace.parse_attempts = round(t_llm["ms"], 1), attempts
        trace.prompt_tokens, trace.completion_tokens = usage["prompt_tokens"], usage["completion_tokens"]
        trace.cost_usd = self._cost(usage)

        if parsed is None:
            trace.parse_ok, trace.abstain_source = False, "parse_failure"
            resp = abstain(f"The model's output could not be validated ({err}).")
            return TriageResult(response=resp, trace=trace, sources=[])

        with self.tel.span("copilot.guardrails") as sp:
            resp = self._postprocess(parsed, hits, trace)
            sp.set(dropped_commands=len(trace.dropped_commands), dropped_citations=len(trace.dropped_citations),
                   flagged_remediation=trace.flagged_remediation, groundedness=trace.groundedness)
        sources = _source_view(hits, resp.citations) if resp.found_answer else _source_view(hits[:3])
        return TriageResult(response=resp, trace=trace, sources=sources)

    def _cost(self, usage: dict) -> float | None:
        """USD estimate from user-supplied per-1M-token prices; None when prices are not configured."""
        pin, pout = self.s.price_in_per_1m, self.s.price_out_per_1m
        if pin is None or pout is None:
            return None
        return round((usage["prompt_tokens"] * pin + usage["completion_tokens"] * pout) / 1_000_000, 6)

    # ------------------------------------------------------------------
    def _postprocess(self, r: TriageResponse, hits: list[RetrievedChunk], trace: Trace) -> TriageResponse:
        if not r.found_answer:
            trace.abstain_source = "llm"
            return abstain(r.answer_not_found_reason or "The model found no supporting evidence.")

        retrieved = {h.chunk.chunk_id: h for h in hits}
        cites, dropped_c = check_citations(r.citations, set(retrieved))
        trace.dropped_citations = dropped_c
        if not cites:
            trace.abstain_source = "no_valid_citations"
            return abstain("The model did not cite any retrieved source, so the answer cannot be verified.")

        cmds, dropped_cmds = filter_commands(r.diagnostic_commands)
        remediation, flagged = sanitize_remediation(r.remediation_guidance)
        trace.dropped_commands, trace.flagged_remediation = dropped_cmds, flagged

        g = groundedness(r.evidence, [retrieved[c].chunk.text for c in cites])
        trace.groundedness = g
        conf = min(r.confidence, 0.2 + 0.8 * g)
        if not r.evidence:
            conf = min(conf, 0.5)
        if conf < self.s.min_confidence:
            trace.abstain_source = "low_confidence"
            return abstain(f"Confidence {conf:.2f} is below the threshold {self.s.min_confidence}.",
                           _normalize_incident_type(r.incident_type))

        return TriageResponse(
            found_answer=True, incident_type=_normalize_incident_type(r.incident_type), summary=r.summary,
            likely_causes=r.likely_causes, evidence=r.evidence, diagnostic_commands=cmds,
            remediation_guidance=remediation, confidence=round(conf, 2), citations=cites,
        )

    def _log(self, question: str, result: TriageResult) -> None:
        if self.log:
            log_request(question, result.trace, result.response.found_answer, result.response.incident_type, self.s)
