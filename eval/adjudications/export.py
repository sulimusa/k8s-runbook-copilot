"""Bind explicit developer review decisions to frozen answers, context and model findings."""
import json
from collections import Counter
from pathlib import Path

from eval.knowledge_value.study import digest, review_packet
from runbook_copilot.config import ROOT


def export():
    decisions = json.loads((Path(__file__).parent/'decisions.json').read_text())
    queue = json.loads((ROOT/'docs/judge-review-queue.json').read_text())
    source = json.loads((ROOT/'docs/knowledge-value-live-claim-reviewed-results.json').read_text())
    cases = {c['id']: c for c in source['cases']}
    packets = {}
    for split in ('development', 'reserved-test'):
        batch, mapping = review_packet(ROOT/'eval/reports'/f'knowledge-value-{split}-v3')
        for ident, case in batch['cases'].items():
            for item in case['candidates']:
                packets[(ident, mapping[ident][item['label']])] = item
    result = {'reviewer': 'Implementation assistant; not an independent human reviewer',
              'scope': 'Every one of the 31 queued findings in the prior 24-case study. Frozen answers and numeric judge ratings remain unchanged. These decisions are not recomputed accuracy scores.',
              'source_sha256': digest(source), 'queue_sha256': digest(queue),
              'sources': ['https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/',
                          'https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/'],
              'decisions': [], 'previous_known_regressions': queue['known_regressions']}
    seen = set()
    for case in queue['cases']:
        for arm, issues in case['candidates'].items():
            for i, issue in enumerate(issues):
                key = f"{case['id']}/{arm}/{i}"
                verdict, reason = decisions[key]
                packet = packets[(case['id'], arm)]
                result['decisions'].append({'id': key, 'finding': issue, 'verdict': verdict, 'reason': reason,
                                            'answer_sha256': digest(cases[case['id']]['answers'][arm]),
                                            'context_sha256': digest(packet['available_context']),
                                            'question': packet['available_context']['question'],
                                            'observations': packet['available_context']['observations'],
                                            'documents': [d['id'] for d in packet['available_context']['documents']]})
                seen.add(key)
    if seen != set(decisions):
        raise ValueError('Decision coverage differs from review queue')
    result['counts'] = dict(Counter(d['verdict'] for d in result['decisions']))
    (ROOT/'docs/judge-adjudications.json').write_text(json.dumps(result, indent=2)+'\n')
    print(result['counts'])


if __name__ == '__main__':
    export()
