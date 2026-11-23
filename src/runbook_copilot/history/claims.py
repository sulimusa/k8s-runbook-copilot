"""Narrow evidence guards for recurring factual errors, not a general truth checker."""
import re
from collections import defaultdict


def final_claim_issues(final, evidence):
    issues = []
    # Deduplicate history/current snapshots of the SAME reported termination.
    terminations = defaultdict(set)
    for record in evidence.values():
        for obj in (record, record.get('before'), record.get('after')):
            if not isinstance(obj, dict) or obj.get('kind') != 'Pod':
                continue
            for status in obj.get('container_status', []):
                if status.get('last_termination', {}).get('reason') == 'OOMKilled' and isinstance(status.get('restart_count'), int):
                    terminations[(obj.get('uid', obj.get('name')), status.get('name'))].add(status.get('restart_count'))
    text = '\n'.join(str(v) for v in final.model_dump().values())
    repeated = re.search(r'(?<!not )\brepeatedly\s+(?:(?:restarts?|restarting)\s+(?:due to|because of)\s+)?OOMKilled\b|\ball (?:three|\d+) restarts? (?:were |are )?(?:caused by |due to )?OOMKilled\b', text, re.I)
    all_count = re.search(r'\ball (three|\d+)\b', text, re.I)
    required = (3 if all_count[1].lower() == 'three' else int(all_count[1])) if all_count else 2
    if repeated and not any(len(counts) >= required for counts in terminations.values()):
        issues.append('Only the last termination reason is evidenced. Report the restart count separately from last termination OOMKilled; do not assign OOM to every/repeated restart. Earlier reasons are unknown. Apply this correction in every field.')
    if re.search(r'\bDNS\b[^.!?\n]{0,65}\bresolve\w*\b[^.!?\n]{0,35}\bPod IP\b', text, re.I):
        issues.append('Do not require Service DNS to resolve to a Pod IP without confirmed headless Service configuration. Standard Service DNS resolves to its ClusterIP. Verify Service type/DNS behavior separately from EndpointSlice addresses and HTTP success.')
    return issues
