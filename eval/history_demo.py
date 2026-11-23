"""Run paired real-model historical investigations. Synthetic snapshots, never mutations."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from runbook_copilot.config import ROOT
from runbook_copilot.history.chat import investigate
from runbook_copilot.history.demo import DemoClient, cases, fixture_digest, retriever


def run(directory):
    directory.mkdir(parents=True, exist_ok=False)
    protocol = {'fixture_sha256': fixture_digest(), 'code_sha256': hashlib.sha256((ROOT / 'src/runbook_copilot/history/chat.py').read_bytes()).hexdigest(),
                'description': 'Same agent, bounded history/current tools, fixed synthetic clock; operational retrieval enabled/disabled. Demonstration, not held-out evaluation.',
                'cases': {}}
    (directory / 'protocol.json').write_text(json.dumps(protocol, indent=2)+'\n')
    for case in cases():
        protocol['cases'][case['id']] = {}
        for arm in ('evidence', 'rag'):
            try:
                report = investigate(case['question'], case['namespace'], case['days'], retriever(case),
                    client=DemoClient(case), knowledge_enabled=arm == 'rag', now=datetime.fromisoformat(case['as_of']))
            except Exception as exc:
                report = {'status': 'failed', 'error_type': type(exc).__name__}
            protocol['cases'][case['id']][arm] = report
            (directory / f"{case['id']}-{arm}.json").write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps({'case': case['id'], 'arm': arm, 'status': report['status']}), flush=True)
    protocol['status'] = 'completed' if all(r['status']=='completed' for c in protocol['cases'].values() for r in c.values()) else 'incomplete'
    (directory / 'results.json').write_text(json.dumps(protocol, indent=2)+'\n')
    return protocol


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = run(args.directory)
    print(json.dumps({'status': result['status']}))
