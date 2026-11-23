"""Local history-run metrics and explicit user feedback; no external service required."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import ROOT


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def usage(report):
    calls = report.get('calls', [])
    def total(field):
        values = [c.get(field) for c in calls]
        return sum(values) if values and all(v is not None for v in values) else None
    return {'model_calls': len(calls), 'tool_calls': len(report.get('trace', [])),
            'retrieval_calls': sum(t['step']['action'] == 'runbook' for t in report.get('trace', [])),
            'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
            'cost_usd': total('cost_usd'),
            'provider_duration_ms': total('duration_ms'),
            'correction_rounds': len(report.get('claim_corrections', []))}


def finish_metrics(report, started):
    report.update(usage(report))
    report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                  duration_ms=round((time.monotonic()-started)*1000, 2))


def load_runs(directory=None, *, bundled=False):
    if bundled:
        result = json.loads((ROOT/'docs/history-demo-results.json').read_text())
        return [r for arms in result['cases'].values() for r in arms.values()]
    root = Path(directory or ROOT/'logs/history-chat')
    reports = []
    for path in sorted(root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
        try:
            report = json.loads(path.read_text())
            if report.get('type') == 'cluster_history_chat':
                reports.append(report)
        except (OSError, ValueError):
            continue  # a partially written record must not take down monitoring
    return reports


def summarize(reports):
    rows = [{**{k:r.get(k) for k in ('run_id','status','namespace','data_origin','knowledge_enabled','duration_ms','finished_at')},
             **usage(r)} for r in reports]
    return {'rows': rows, 'runs': len(rows),
            'failures': sum(r['status'] != 'completed' for r in rows),
            'known_cost_usd': sum(r['cost_usd'] for r in rows if r['cost_usd'] is not None),
            'unknown_cost_runs': sum(r['cost_usd'] is None for r in rows),
            'scope': 'Selected investigations only; judges and other runs are excluded. Provider latency is not end-to-end latency. Older reports may lack end-to-end timing.'}


def feedback_db(path=None):
    path = Path(path or ROOT/'logs/history-feedback.sqlite')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, run_id TEXT, answer_sha256 TEXT, rating TEXT, correction TEXT, created_at TEXT, reviewer TEXT)')
    return db


def save_feedback(report, rating, correction='', path=None):
    if rating not in ('Useful', 'Not useful', 'Needs review') or len(correction) > 2000:
        raise ValueError('Invalid feedback')
    if report.get('status') != 'completed' or not report.get('structured'):
        raise ValueError('Feedback requires a completed answer')
    uuid.UUID(report['run_id'])
    row = {'id':str(uuid.uuid4()), 'run_id':report['run_id'], 'answer_sha256':fingerprint(report['structured']),
           'rating':rating, 'correction':correction.strip(), 'created_at':datetime.now(timezone.utc).isoformat(),
           'reviewer':'local user (not authenticated identity)'}
    db=feedback_db(path)
    try:
        with db:
            db.execute('INSERT INTO feedback VALUES (:id,:run_id,:answer_sha256,:rating,:correction,:created_at,:reviewer)',row)
    finally:
        db.close()
    return row


def read_feedback(path=None):
    db=feedback_db(path)
    db.row_factory=sqlite3.Row
    try:
        return [dict(r) for r in db.execute('SELECT * FROM feedback ORDER BY created_at DESC LIMIT 200')]
    finally:
        db.close()


def regression_candidate(report, feedback):
    if feedback['run_id'] != report['run_id'] or feedback['answer_sha256'] != fingerprint(report['structured']):
        raise ValueError('Feedback does not match this answer')
    return {'status':'requires_human_ground_truth_review', 'source_run_id':report['run_id'],
            'answer_sha256':feedback['answer_sha256'], 'question':report['question'],
            'answer':report['structured'], 'evidence':report['citations'],
            'feedback':feedback, 'expected_answer':None,
            'instruction':'Review and label before adding to evaluation. Never ingest answer keys into retrieval.'}
