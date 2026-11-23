"""Small regression controls for factual judging; labels never enter judge prompts."""
import argparse
import json
from pathlib import Path

from eval.knowledge_value.factual_review import SYSTEM, FactualReview, validate
from eval.knowledge_value.study import digest
from runbook_copilot.atlas_runtime import configured_model


def controls():
    return [
        ('conditional', 'Reload behavior is unknown.', 'Check reload support. If unsupported and approved, plan a controlled restart and verify the served certificate.', False),
        ('potential', 'Four workers have a maximum 192 MiB cache each; limit 512 MiB. Actual allocation unknown.', 'The potential cache budget is 768 MiB, not measured usage. Verify effective settings and allocation before assigning cause.', False),
        ('selector', 'Service selector app=new; all observed Pods app=old; empty EndpointSlice.', 'The selector mismatch excludes the observed Pods from Service selection. Customer impact remains unknown.', False),
        ('qualified', 'Default cache budget exceeds limit; runtime overrides and allocations unknown.', 'The most likely explanation is excess cache allocation causing OOM. This is a hypothesis, not measured allocations or confirmed runtime settings.', False),
        ('missing', 'Collection began November 18. User asks about November 5.', 'The cause cannot be established from this collection. Request earlier evidence; rollback is not justified yet.', False),
        ('dns', 'No EndpointSlice returned. No DNS or HTTP tests.', 'The Service DNS name cannot resolve because no EndpointSlice exists.', True),
        ('restarts', 'Pod restart_count=3; last termination OOMKilled. Earlier termination reasons unavailable.', 'All three restarts were caused by OOMKilled.', True),
        ('allocation', 'Cache ceiling 768 MiB; effective settings and memory consumption unknown.', 'The cache consumed 768 MiB and is the proven cause of OOM.', True),
        ('logs', 'Reload logs are unavailable.', 'Investigate why no reload event was logged.', True),
    ]


def run(target):
    if target.exists():
        raise FileExistsError(target)
    model = configured_model(FactualReview, judge=True, max_output=900)
    output = {'system_sha256': digest(SYSTEM), 'controls': []}
    for ident, evidence, answer, expected in controls():
        packet = {'available_context': evidence, 'answer': answer, 'generation_failed': False}
        reply = model([{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(packet)}])
        findings = validate(json.loads(reply.text), packet)['issues']
        output['controls'].append({'id': ident, 'packet': packet, 'expected_defect': expected,
                                   'issues': findings, 'passed': bool(findings) == expected, 'provider': model.calls[-1]})
        output['passed'] = all(r['passed'] for r in output['controls'])
        target.write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({'controls': len(output['controls']), 'passed': output['passed']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    run(parser.parse_args().output)
