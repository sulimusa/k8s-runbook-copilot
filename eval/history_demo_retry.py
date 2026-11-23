"""Retry only failed demo arms; retain successful originals and explicit per-arm provenance."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from runbook_copilot.config import ROOT
from runbook_copilot.history.chat import investigate
from runbook_copilot.history.demo import DemoClient, cases, fixture_digest, retriever


def retry(source, target):
    original = json.loads((source/'results.json').read_text())
    if original['fixture_sha256'] != fixture_digest():
        raise ValueError('Fixtures changed; cannot mix comparisons')
    chat_hash = hashlib.sha256((ROOT/'src/runbook_copilot/history/chat.py').read_bytes()).hexdigest()
    if original['code_sha256'] != chat_hash:
        raise ValueError('Investigator changed; cannot reuse earlier arms')
    target.mkdir(parents=True, exist_ok=False)
    result = {**original, 'retry_source': str(source), 'per_arm_source': {},
              'retry_reason': 'A narrow repeated-OOM guard incorrectly rejected a qualified statement spanning a semicolon. Corrected guard and regression-tested; successful answers retained without editing.',
              'retry_guard_sha256': hashlib.sha256((ROOT/'src/runbook_copilot/history/claims.py').read_bytes()).hexdigest()}
    for case in cases():
        ident = case['id']
        for arm, old in original['cases'][ident].items():
            new = old
            provenance = str(source)
            if old['status'] != 'completed':
                new = investigate(case['question'],case['namespace'],case['days'],retriever(case),
                                  client=DemoClient(case),knowledge_enabled=arm=='rag',now=datetime.fromisoformat(case['as_of']))
                provenance = str(target)
            result['cases'][ident][arm] = new
            result['per_arm_source'][ident+'/'+arm] = provenance
            (target/f'{ident}-{arm}.json').write_text(json.dumps(new,indent=2)+'\n')
    result['status'] = 'completed' if all(r['status']=='completed' for c in result['cases'].values() for r in c.values()) else 'incomplete'
    (target/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('target',type=Path)
    args = p.parse_args()
    retry(args.source,args.target)
