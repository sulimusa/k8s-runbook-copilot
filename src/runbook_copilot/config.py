"""Central settings. Everything configurable comes from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    sources_file: Path = ROOT / "data" / "sources.yaml"
    lock_file: Path = ROOT / "data" / "sources.lock.json"
    raw_dir: Path = ROOT / "data" / "raw"
    chunks_path: Path = ROOT / "data" / "processed" / "chunks.jsonl"
    index_dir: Path = ROOT / "data" / "index"
    log_path: Path = ROOT / "logs" / "requests.jsonl"
    agent_audit_path: Path = ROOT / "logs" / "agent-audit.jsonl"

    # LLM (any OpenAI-compatible endpoint)
    llm_base_url: str = field(default_factory=lambda: os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_api_key: str = field(default_factory=lambda: os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "")))
    llm_model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "gpt-4o-mini"))
    embed_model: str = field(default_factory=lambda: os.environ.get("EMBED_MODEL", ""))

    # Retrieval + gate
    top_k: int = field(default_factory=lambda: _i("TOP_K", 6))
    min_bm25_score: float = field(default_factory=lambda: _f("MIN_BM25_SCORE", 4.0))
    min_query_coverage: float = field(default_factory=lambda: _f("MIN_QUERY_COVERAGE", 0.4))
    strong_match_score: float = field(default_factory=lambda: _f("STRONG_MATCH_SCORE", 20.0))
    min_confidence: float = field(default_factory=lambda: _f("MIN_CONFIDENCE", 0.35))
    max_context_chars: int = 14000
    max_question_chars: int = 2000

    # Deployment identity (attached to every trace and metric)
    app_env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "local"))
    app_version: str = field(default_factory=lambda: os.environ.get("APP_VERSION", "dev"))
    # OpenTelemetry is off unless enabled; endpoint comes from the standard OTEL_EXPORTER_OTLP_ENDPOINT variable
    otel_enabled: bool = field(default_factory=lambda: os.environ.get("OTEL_ENABLED", "false").lower() == "true")
    # Optional USD price per 1M tokens, copied from your provider's pricing page (never hard-coded here: prices change)
    price_in_per_1m: float | None = field(default_factory=lambda: float(os.environ["LLM_PRICE_IN_PER_1M"]) if os.environ.get("LLM_PRICE_IN_PER_1M") else None)
    price_out_per_1m: float | None = field(default_factory=lambda: float(os.environ["LLM_PRICE_OUT_PER_1M"]) if os.environ.get("LLM_PRICE_OUT_PER_1M") else None)

    log_questions: bool = field(default_factory=lambda: os.environ.get("LOG_QUESTIONS", "false").lower() == "true")

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)


def get_settings() -> Settings:
    return Settings()
