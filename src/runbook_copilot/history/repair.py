"""One explicit dev repair. No free-form command, no production mutation, no model-written patch."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..agent.actions import PatchServiceSelector
from ..agent.policy import Context, Policy
from ..agent.runner import KubectlRunner
from ..config import ROOT
from .store import now


class DevRepair:
    def __init__(self, expected_uid, runner=None):
        self.uid = expected_uid
        self.runner = runner or KubectlRunner(context='kind-runbook-capstone-dev',
                                             kubeconfig=str(ROOT / '.agent/capstone-dev.kubeconfig'))

    def read(self, args):
        result = self.runner.run(['get', *args, '-o', 'json'])
        if not result.ok:
            raise RuntimeError('Restricted Kubernetes read failed; check dev access token')
        return json.loads(result.stdout)

    def restore(self, namespace, record):
        if namespace != 'dev-capstone' or record.get('namespace') != namespace:
            raise ValueError('Production is read-only; fixes are limited to dev-capstone')
        if record.get('kind') != 'Service' or record.get('operation') not in ('MODIFIED', 'RECONCILED'):
            raise ValueError('Choose a recorded Service change with a prior selector')
        before = record.get('before') or {}
        if not before.get('selector_complete') or not before.get('selector'):
            raise ValueError('No complete prior selector available')
        if self.read(['namespace', 'kube-system'])['metadata']['uid'] != self.uid:
            raise ValueError('Cluster identity mismatch; refusing repair')
        ns = self.read(['namespace', namespace])
        current = self.read(['service', record['name'], '-n', namespace])
        if current['metadata']['uid'] != record['uid'] or current['metadata']['resourceVersion'] != record['rv']:
            raise ValueError('Service changed since this history record; refresh and investigate again')
        old = current['spec'].get('selector', {})
        target = before['selector']
        if old == target:
            raise ValueError('Selector already matches proposed restoration')
        pods = self.read(['pods', '-n', namespace])['items']
        action = PatchServiceSelector(type='patch_service_selector', namespace=namespace,
                                      name=record['name'], selector=target)
        policy = Policy.load('dev')
        ns_decision = policy.check_namespace(namespace, ns['metadata'].get('labels', {}))
        decision = policy.check_action(action, Context(target=current, pod_labels=[p['metadata'].get('labels', {}) for p in pods]))
        if not policy.check_kube_context(self.runner.current_context()).allowed or not ns_decision.allowed or not decision.allowed:
            raise ValueError('Dev policy rejected restoration')
        patch = self.patch(current, target)
        args = ['patch', 'service', record['name'], '-n', namespace, '--type=json', '-p', json.dumps(patch)]
        if not self.runner.run([*args, '--dry-run=server']).ok:
            raise RuntimeError('Server dry run rejected the change')
        applied = self.runner.run([*args, '-o', 'json'])
        if not applied.ok:
            raise RuntimeError('Service changed or patch was rejected; nothing further attempted')
        applied_object = json.loads(applied.stdout)
        applied_rv = applied_object['metadata']['resourceVersion']
        outcome = 'verification_failed'
        try:
            for _ in range(12):
                time.sleep(2)
                latest = self.read(['service', record['name'], '-n', namespace])
                if latest['metadata']['resourceVersion'] != applied_rv:
                    outcome = 'concurrent_change_detected_no_rollback'
                    break
                slices = self.read(['endpointslices', '-n', namespace, '-l', f'kubernetes.io/service-name={record["name"]}'])
                if any(e.get('conditions', {}).get('ready') is True
                       for s in slices['items'] for e in (s.get('endpoints') or [])):
                    outcome = 'ready_endpoints_restored'
                    break
        except Exception:
            outcome = 'verification_read_failed'
        if outcome not in ('ready_endpoints_restored', 'concurrent_change_detected_no_rollback'):
            try:
                latest = self.read(['service', record['name'], '-n', namespace])
                if latest['metadata']['uid'] == record['uid'] and latest['metadata']['resourceVersion'] == applied_rv:
                    rollback = self.runner.run(['patch', 'service', record['name'], '-n', namespace,
                                                '--type=json', '-p', json.dumps(self.patch(latest, old))])
                    outcome = 'rolled_back_after_failed_verification' if rollback.ok else 'rollback_failed'
                else:
                    outcome = 'concurrent_change_detected_no_rollback'
            except Exception:
                outcome = 'rollback_unavailable_manual_check_required'
        result = {'at': now(), 'cluster_uid': self.uid, 'namespace': namespace, 'service': record['name'],
                  'history_id': record['id'], 'old_selector': old, 'new_selector': target, 'outcome': outcome,
                  'verification': 'Ready EndpointSlice endpoint only; not an application-level transaction test.'}
        path = Path(ROOT) / 'logs/history-repairs.jsonl'
        path.parent.mkdir(exist_ok=True)
        with path.open('a') as f:
            f.write(json.dumps(result) + '\n')
        return result

    @staticmethod
    def patch(obj, selector):
        return [{'op': 'test', 'path': '/metadata/uid', 'value': obj['metadata']['uid']},
                {'op': 'test', 'path': '/metadata/resourceVersion', 'value': obj['metadata']['resourceVersion']},
                {'op': 'test', 'path': '/spec/selector', 'value': obj['spec'].get('selector', {})},
                {'op': 'replace', 'path': '/spec/selector', 'value': selector}]
