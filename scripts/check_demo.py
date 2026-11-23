"""Offline integrity checks for recorded investigation artifacts; never calls a model."""
import json
from pathlib import Path

from runbook_copilot.history.demo import fixture_digest
from runbook_copilot.history.monitoring import fingerprint, summarize

root=Path(__file__).resolve().parents[1]
results=json.loads((root/'docs/history-demo-results.json').read_text())
review=json.loads((root/'docs/history-demo-adjudications.json').read_text())
assert results['fixture_sha256']==fixture_digest(), 'Demo fixtures changed since recorded runs'
assert review['results_sha256']==fingerprint(results), 'Review no longer matches the published answers'
reports=[]
for ident,arms in results['cases'].items():
    assert set(arms)=={'evidence','rag'}
    for arm,r in arms.items():
        assert r['status']=='completed'
        assert review['cases'][ident][arm]['answer_sha256']==fingerprint(r['structured'])
        assert r['data_origin']=='synthetic_history_snapshot'
        assert all(t['step']['action'] in ('history','current','runbook') for t in r['trace'])
        if arm=='evidence':
            assert all(t['step']['action']!='runbook' for t in r['trace'])
        for t in r['structured']['timeline']:
            assert r['citations'][t['evidence_id']]['observed_at']==t['observed_at']
        reports.append(r)
assert len(reports)==6
cases=json.loads((root/'eval/knowledge_value/cases.json').read_text())
keys=json.loads((root/'eval/knowledge_value/answer_keys.json').read_text())
assert len(cases)==24 and {c['id'] for c in cases}=={c['id'] for c in keys}
for path in ('uv.lock','Dockerfile.demo','docs/getting-started.md','docs/demo-script.md','docs/judge-adjudications.json'):
    assert (root/path).is_file(),f'Missing {path}'
print(json.dumps({'status':'passed','recorded_model_runs':len(reports),'broader_evaluation_cases':len(cases),
                  'recorded_investigation_cost_usd':summarize(reports)['known_cost_usd'],
                  'scope':'Offline artifact integrity, not new AI evaluation, human review or published CI.'},indent=2))
