"""LLM helpers. Works with any OpenAI-compatible chat endpoint.

`LLM` is just a callable: messages -> raw text. That keeps the pipeline testable (pass a fake)
and provider-agnostic (swap base URL / model via env vars).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from openai import OpenAI
from pydantic import ValidationError

from ..config import Settings, get_settings
from ..schemas import TriageResponse


@dataclass
class LLMReply:
    """Model text plus token usage. LLM callables may return a bare str (tests, simple providers) or this."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


LLM = Callable[[list[dict]], str | LLMReply]


class LLMNotConfigured(RuntimeError):
    pass


def make_llm(settings: Settings | None = None, timeout: float = 60.0) -> LLM:
    s = settings or get_settings()
    if not s.llm_configured:
        raise LLMNotConfigured("Set LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL) in .env")
    client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=timeout)

    def call(messages: list[dict]) -> LLMReply:
        kwargs = {"model": s.llm_model, "messages": messages, "temperature": 0}
        try:
            resp = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
        except Exception as e:  # some compatible servers reject response_format; retry without it
            if "response_format" in str(e).lower() or "json" in str(e).lower():
                resp = client.chat.completions.create(**kwargs)
            else:
                raise
        usage = getattr(resp, "usage", None)
        return LLMReply(
            text=resp.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    return call


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(raw: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and leading/trailing prose."""
    text = _FENCE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def generate_model(llm: LLM, messages: list[dict], model_cls, max_attempts: int = 2):
    """Call the LLM and validate the JSON against any Pydantic model. On failure, show the model its own error and retry.

    Returns (obj_or_None, attempts_used, last_error, usage) where usage sums tokens over all attempts.
    """
    msgs = list(messages)
    last_err = None
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for attempt in range(1, max_attempts + 1):
        reply = llm(msgs)
        raw = reply.text if isinstance(reply, LLMReply) else reply
        if isinstance(reply, LLMReply):
            usage["prompt_tokens"] += reply.prompt_tokens
            usage["completion_tokens"] += reply.completion_tokens
        try:
            return model_cls.model_validate(extract_json(raw)), attempt, None, usage
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = str(e)[:600]
            msgs = msgs + [
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content": f"Your output was invalid: {last_err}\nReturn ONLY the corrected JSON object."},
            ]
    return None, max_attempts, last_err, usage


def generate_triage(llm: LLM, messages: list[dict], max_attempts: int = 2):
    """Triage-specific wrapper: (TriageResponse | None, attempts, last_error, usage)."""
    return generate_model(llm, messages, TriageResponse, max_attempts)
