"""Bounded, auditable provider calls for investigations, separate from generic triage."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from openai import OpenAI

from .config import ROOT, get_settings
from .llm.client import LLMNotConfigured, LLMReply


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Reserve conservative cost before sending; retain reservation on unknown outcomes."""

    def __init__(self, path: Path, limit: float):
        if not math.isfinite(limit) or not 0 < limit <= 10:
            raise ValueError('Budget must be explicit, positive and at most $10')
        self.path, self.limit = path, limit
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY, cap REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, charged REAL, actual REAL)')
            db.execute('INSERT OR IGNORE INTO budget VALUES (1, ?)', (limit,))
            if db.execute('SELECT cap FROM budget WHERE id=1').fetchone()[0] != limit:
                raise ValueError('Existing campaign budget differs; do not silently reset it')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, amount):
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError('Invalid reservation')
        ident = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            used = db.execute('SELECT COALESCE(SUM(charged),0) FROM calls').fetchone()[0]
            if used + amount > self.limit:
                raise BudgetExceeded('Campaign budget would be exceeded')
            db.execute('INSERT INTO calls VALUES (?,?,NULL)', (ident, amount))
        return ident

    def settle(self, ident, actual):
        if not math.isfinite(actual) or actual < 0:
            raise ValueError('Invalid cost')
        with self.connect() as db:
            db.execute('UPDATE calls SET charged=?, actual=? WHERE id=?', (actual, actual, ident))

    def summary(self):
        with self.connect() as db:
            charged, actual, unknown = db.execute(
                'SELECT COALESCE(SUM(charged),0), COALESCE(SUM(actual),0), '
                'SUM(CASE WHEN actual IS NULL THEN 1 ELSE 0 END) FROM calls').fetchone()
        return {'limit_usd': self.limit, 'charged_or_reserved_usd': charged,
                'known_cost_usd': actual, 'unknown_outcomes': unknown or 0}


def strict_schema(schema):
    """All properties required for provider strict mode; defaults still handled by Pydantic."""
    if isinstance(schema, dict):
        out = {k: strict_schema(v) for k, v in schema.items() if k != 'default'}
        if out.get('type') == 'object':
            out['additionalProperties'] = False
            out['required'] = list(out.get('properties', {}))
        return out
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


class BoundedModel:
    def __init__(self, schema, *, model, key, budget, input_price, output_price,
                 client=None, max_output=2200):
        if not key:
            raise LLMNotConfigured('Configure the LLM_API_KEY locally')
        if not 128 <= max_output <= 4096:
            raise ValueError('Output limit outside configured bounds')
        if not all(math.isfinite(p) and p > 0 for p in (input_price, output_price)):
            raise ValueError('Configure positive, verified token prices')
        self.client = client or OpenAI(api_key=key, max_retries=0, timeout=45)
        self.schema = strict_schema(schema.model_json_schema())
        self.budget, self.prices = budget, (input_price, output_price)
        self.model, self.max_output, self.calls = model, max_output, []
        self.metadata = {'requested_model': model, 'temperature': 0, 'max_completion_tokens': max_output,
                         'sdk_retries': 0, 'response_format': 'json_schema',
                         'input_price_per_million': input_price, 'output_price_per_million': output_price}

    def __call__(self, messages):
        payload = json.dumps({'messages': messages, 'schema': self.schema}, ensure_ascii=False)
        # Text-only messages. UTF-8 byte count + framing reserve intentionally overestimates tokens.
        upper_input = len(payload.encode()) + 4096
        if upper_input > 200000:
            raise ValueError('Model context exceeds the configured input bound')
        reserve = (upper_input * self.prices[0] + self.max_output * self.prices[1]) / 1e6
        ident = self.budget.reserve(reserve)
        record = {'prompt_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                  'requested_model': self.model, 'reserved_usd': reserve,
                  'input_tokens': None, 'output_tokens': None, 'cost_usd': None}
        self.calls.append(record)
        started = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0,
                max_completion_tokens=self.max_output,
                response_format={'type': 'json_schema', 'json_schema': {
                    'name': 'investigation_response', 'strict': True, 'schema': self.schema}})
            record.update(resolved_model=response.model, response_id=response.id)
            usage = response.usage
            if usage is None:
                raise RuntimeError('Provider did not return usage; reservation retained')
            cost = (usage.prompt_tokens * self.prices[0] + usage.completion_tokens * self.prices[1]) / 1e6
            self.budget.settle(ident, cost)
            record.update(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, cost_usd=cost)
            choice = response.choices[0]
            if choice.finish_reason != 'stop' or getattr(choice.message, 'refusal', None):
                raise RuntimeError('Provider refused or truncated output')
            return LLMReply(choice.message.content or '', usage.prompt_tokens, usage.completion_tokens)
        except Exception as exc:
            # Never persist a provider exception body: it can contain headers or request content.
            record['error_type'] = type(exc).__name__
            raise
        finally:
            record['duration_ms'] = round((time.monotonic() - started) * 1000, 2)


def configured_model(schema, *, judge=False, max_output=2200):
    settings = get_settings()
    cap = float(os.environ.get('ATLAS_BUDGET_USD', '0'))
    budget = Budget(ROOT / 'logs/atlas-budget.sqlite', cap)
    model = os.environ.get('ATLAS_JUDGE_MODEL' if judge else 'ATLAS_MODEL', settings.llm_model)
    return BoundedModel(schema, model=model, key=settings.llm_api_key, budget=budget, max_output=max_output,
                        input_price=float(os.environ.get('ATLAS_INPUT_PRICE', '0')),
                        output_price=float(os.environ.get('ATLAS_OUTPUT_PRICE', '0')))


def save_report(report, directory=None):
    directory = Path(directory or ROOT / 'logs/atlas-runs')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (report['run_id'] + '.json')
    with path.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    return path
