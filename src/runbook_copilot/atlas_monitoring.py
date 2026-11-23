"""Persistent local run dashboard; telemetry export is optional, report persistence is not."""
import html
import json
from pathlib import Path

from .config import ROOT


def judge_summary(directory=None):
    directory = Path(directory or ROOT / 'eval/reports')
    rows = []
    for path in sorted(directory.glob('*/judge-results.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
        try:
            result = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue  # an in-progress report is not a finished evaluation
        for case, review in result['cases'].items():
            rows.append({'batch': path.parent.name, 'case': case, 'passed': review['passed'],
                         'human_review': review['human_review']})
    return rows


def summary(directory=None):
    directory = Path(directory or ROOT / 'logs/atlas-runs')
    rows = []
    for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
        report = json.loads(path.read_text())
        rows.append({k: report.get(k) for k in ('run_id', 'case', 'planner', 'mode', 'status', 'termination',
                                               'started_at', 'duration_ms', 'model_calls', 'tool_calls',
                                               'input_tokens', 'output_tokens', 'cost_usd', 'trace_id')})
    return {'runs': rows, 'count': len(rows), 'limit': 200,
            'errors': sum(r['status'] in ('error', 'denied') for r in rows),
            'known_cost_usd': sum(r['cost_usd'] for r in rows if r['cost_usd'] is not None),
            'unknown_cost_runs': sum(r['planner'] == 'model' and r['cost_usd'] is None for r in rows)}


def dashboard(directory=None):
    data = summary(directory)
    rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(r[k])) + '</td>' for k in (
        'case', 'planner', 'status', 'model_calls', 'tool_calls', 'duration_ms', 'cost_usd'))
        + '<td><a href="/atlas/runs/' + html.escape(str(r['run_id']), quote=True)
        + '">Report</a></td></tr>' for r in data['runs'])
    judgments = ''.join('<tr>' + ''.join('<td>' + html.escape(str(v)) + '</td>'
                         for v in (r['batch'], r['case'], 'Pass' if r['passed'] else 'Fail', r['human_review']))
                         + '</tr>' for r in judge_summary())
    return ('<html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="15">'
            '<title>Atlas monitoring</title><style>body{font:16px system-ui;margin:40px;background:#101820;color:#e6edf3}'
            'td,th{padding:12px;text-align:left;border-bottom:1px solid #567}a{color:#7acfff}</style>'
            '<h1>Atlas investigation monitoring</h1><p>Persistent local reports · latest 200 runs · synthetic evidence</p>'
            f'<p>Runs: {data["count"]} · Errors/denials: {data["errors"]} · '
            f'Investigation cost (excluding judges): ${data["known_cost_usd"]:.5f} · Unknown-cost model runs: {data["unknown_cost_runs"]}</p>'
            '<p><a href="/demo/rollout-oom">Run an investigation</a> · <a href="/atlas/stats">JSON metrics</a></p>'
            '<h2>Independent judge + deterministic checks</h2>'
            '<p>Development cases; human review pending. Pass is not a general accuracy claim.</p>'
            '<table><tr><th>Batch</th><th>Case</th><th>Combined result</th><th>Human review</th></tr>'
            + judgments + '</table><h2>Investigation history</h2>'
            '<table><tr><th>Case</th><th>Planner</th><th>Outcome</th><th>Model calls</th><th>Tools</th>'
            '<th>Milliseconds</th><th>USD</th><th>Evidence</th></tr>' + rows + '</table></html>')
