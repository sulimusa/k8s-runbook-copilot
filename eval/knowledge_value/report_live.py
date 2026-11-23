"""Export a reproducible, reviewable summary without changing frozen study assets."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median

from eval.knowledge_value.study import (
    ARMS,
    DIMENSIONS,
    digest,
    load,
    prediction,
    read,
    review_packet,
    validate_judgment,
)
from runbook_copilot.config import ROOT


def collect(directories, *, context_review=False, review_folder='judgments-context-aware-v2'):
    cases, runs, spending = [], [], {'generation': 0.0, 'judge': 0.0}
    models = set()
    for directory in map(Path, directories):
        manifest = load(directory)
        packet, mapping = review_packet(directory)
        report = read(directory / 'answer-quality-report.json')
        if report['missing_judgments']:
            raise ValueError('Incomplete judge results cannot become a complete comparison')
        runs.append({'directory': str(directory.relative_to(ROOT)), 'split': manifest['split'],
                     'manifest_sha256': digest(manifest), 'report_sha256': digest(report)})
        originals = {c['id']: c for c in read(directory / 'cases.json')}
        protocol = None
        if context_review:
            protocol = read(directory / review_folder / 'protocol.json')
            if protocol['packet_sha256'] != digest(packet):
                raise ValueError('Supplemental review packet changed')
            runs[-1]['supplemental_protocol_sha256'] = digest(protocol)
        for row in report['cases']:
            ident = row['id']
            preds = {arm: prediction(directory, ident, arm) for arm in ARMS}
            judge = read(directory / (review_folder if context_review else 'judgments') / f'{ident}.json')
            if context_review:
                if judge['error'] or judge['packet_sha256'] != digest(packet['cases'][ident]) or judge['system_sha256'] != protocol['system_sha256']:
                    raise ValueError('Invalid supplemental judgment')
                validate_judgment(judge['judgment'], packet['cases'][ident])
            scores = {mapping[ident][c['label']]: c for c in judge['judgment']['candidates']}
            spending['judge'] += judge['provider']['cost_usd']
            for pred in preds.values():
                spending['generation'] += pred['provider']['cost_usd'] or 0
                if pred['provider'].get('resolved_model'):
                    models.add(pred['provider']['resolved_model'])
            effective = {a: {d: scores[a][d]['score'] for d in DIMENSIONS} for a in ARMS}
            row = {**row, 'scores': effective,
                   'rag_minus_evidence': {d: effective['rag'][d] - effective['evidence'][d] for d in DIMENSIONS},
                   'unsupported_claims': {a: scores[a]['unsupported_claims'] for a in ARMS}}
            cases.append({**row, 'split': manifest['split'], 'question': originals[ident]['question'],
                'scope': originals[ident]['scope'], 'observations': originals[ident]['evidence'],
                'reference': packet['cases'][ident]['reference'],
                'answers': {a: p['answer'] for a, p in preds.items()},
                'errors': {a: p['error'] for a, p in preds.items()},
                'judge_rationales': {a: {d: scores[a][d]['rationale'] for d in DIMENSIONS} for a in ARMS},
                'usage': {a: {k: p['provider'].get(k) for k in ('input_tokens', 'output_tokens', 'cost_usd', 'duration_ms')}
                          for a, p in preds.items()},
                'retrieved_documents': [{k: d[k] for k in ('id', 'title', 'url')} for c in packet['cases'][ident]['candidates']
                                        if mapping[ident][c['label']] == 'rag' for d in c['available_context']['documents']]})
    if len(models) != 1 or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Inconsistent model or duplicate cases')
    summary = {}
    for category in sorted({c['category'] for c in cases}):
        members = [c for c in cases if c['category'] == category]
        summary[category] = {'cases': len(members),
            'mean_scores': {a: {d: mean(c['scores'][a][d] for c in members) for d in DIMENSIONS} for a in ARMS},
            'usefulness_rag_vs_evidence': dict(Counter('win' if c['rag_minus_evidence']['usefulness'] > 0 else
                'loss' if c['rag_minus_evidence']['usefulness'] < 0 else 'tie' for c in members)),
            'any_dimension_regressions': [c['id'] for c in members if any(v < 0 for v in c['rag_minus_evidence'].values())]}
    telemetry = {a: {'median_latency_ms': median(c['usage'][a]['duration_ms'] for c in cases),
                     'input_tokens': sum(c['usage'][a]['input_tokens'] or 0 for c in cases),
                     'output_tokens': sum(c['usage'][a]['output_tokens'] or 0 for c in cases),
                     'failures': sum(bool(c['errors'][a]) for c in cases)} for a in ARMS}
    return {'status': 'completed model comparison; human review pending',
            'review_pass': review_folder.removeprefix('judgments-') if context_review else 'original (known context-penalty bias)', 'model': next(iter(models)),
            'runs': runs, 'case_count': len(cases), 'summary': summary, 'telemetry': telemetry,
            'study_cost_usd': spending, 'cases': cases,
            'limitations': ['Synthetic service contracts and author-aware family-disjoint splits.',
                'One generation per case/arm; same-provider label-blinded judge, no independent human ground truth review.',
                'Primary comparison isolates retrieval over frozen observations, not live cluster agent performance.',
                'Scores are ordinal judge ratings, not accuracy percentages or calibrated probabilities.',
                'Token costs use standard non-cached rates and may conservatively exceed the eventual invoice.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context-review', action='store_true')
    args = parser.parse_args()
    directories = [ROOT / 'eval/reports' / f'knowledge-value-{s}-v3' for s in ('development', 'reserved-test')]
    result = collect(directories, context_review=args.context_review)
    target = ROOT / ('docs/knowledge-value-live-context-reviewed-results.json' if args.context_review else 'docs/knowledge-value-live-results.json')
    with target.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
