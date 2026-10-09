"""Pydantic models shared across ingestion, retrieval, the pipeline, the API and the eval harness."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

# The closed set of incident types the model may choose from. "Unknown" is used on abstention.
INCIDENT_TYPES = [
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "OOMKilled",
    "PodPending",
    "ProbeFailure",
    "DNSServiceConnectivity",
    "FailedRollout",
    "ResourceQuotaOrNodePressure",
    "Unknown",
]


class TriageResponse(BaseModel):
    """The contract between the LLM and the rest of the system."""

    found_answer: bool
    incident_type: str
    summary: str
    likely_causes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    diagnostic_commands: list[str] = Field(default_factory=list)
    remediation_guidance: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)
    answer_not_found_reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> TriageResponse:
        if self.found_answer and not self.citations:
            raise ValueError("found_answer=true requires at least one citation (chunk_id)")
        if not self.found_answer and not self.answer_not_found_reason:
            raise ValueError("found_answer=false requires answer_not_found_reason")
        return self


class Chunk(BaseModel):
    chunk_id: str  # stable, human-readable: "<source_id>:<doc path without ext>#<nn>"
    source_id: str
    doc_path: str  # path relative to the repo root of the source
    url: str
    title: str
    heading_path: str
    text: str
    license: str
    commit_sha: str
    tags: list[str] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float  # final ranking score (fused when hybrid)
    bm25: float  # raw keyword score, used by the abstention gate


class TriageRequest(BaseModel):
    question: str


class Trace(BaseModel):
    """Per-request diagnostics. Returned by the API and written to the JSONL log."""

    latency_ms: float = 0.0
    retrieval_ms: float = 0.0
    llm_ms: float = 0.0
    top_bm25: float = 0.0
    query_coverage: float = 0.0
    gate_ok: bool = True
    gate_reason: str | None = None
    abstain_source: str | None = None  # gate | llm | low_confidence | no_valid_citations | parse_failure
    parse_ok: bool = True
    parse_attempts: int = 0
    retrieved_ids: list[str] = Field(default_factory=list)
    dropped_citations: list[str] = Field(default_factory=list)
    dropped_commands: list[str] = Field(default_factory=list)
    flagged_remediation: int = 0
    groundedness: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    trace_id: str | None = None  # OpenTelemetry trace id, to jump from a log line to the trace


class TriageResult(BaseModel):
    response: TriageResponse
    trace: Trace
    sources: list[dict] = Field(default_factory=list)  # [{chunk_id, title, url, license}]


class EvalCase(BaseModel):
    id: str
    category: str
    question: str
    expected_incident_type: str
    expected_sources: list[str] = Field(default_factory=list)  # substrings of doc_path
    must_include: list[str] = Field(default_factory=list)  # "a|b" means either a or b
    prohibited: list[str] = Field(default_factory=list)  # substrings that must NOT appear
    found_answer: bool = True
