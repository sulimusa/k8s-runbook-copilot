"""Install ONLY in the explicitly named local investigation cluster. Never uses the default context."""
import copy
import json
import os
import subprocess  # nosec B404: fixed argv, explicit lab kubeconfig, no shell
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KUBECONFIG = ROOT / '.agent/capstone-admin.kubeconfig'
K = ['kubectl', '--kubeconfig', str(KUBECONFIG), '--context', 'kind-runbook-capstone']


def command(args):
    return subprocess.check_output(K + args, text=True)  # nosec B603: caller supplies only fixed operator commands


def apply(obj):
    subprocess.run(K + ['apply', '-f', '-'], input=json.dumps(obj), text=True, check=True, capture_output=True)  # nosec B603: manifest on stdin; fixed argv


def resource(kind, name, namespace=None, **fields):
    api = 'v1'
    if kind in ('Role', 'RoleBinding', 'ClusterRole', 'ClusterRoleBinding'):
        api = 'rbac.authorization.k8s.io/v1'
    if kind == 'Deployment':
        api = 'apps/v1'
    return {'apiVersion': api, 'kind': kind, 'metadata': {'name': name, **({'namespace': namespace} if namespace else {})}, **fields}


def main():
    nodes = json.loads(command(['get', 'nodes', '-o', 'json']))['items']
    if not nodes or any(not n['metadata']['name'].startswith('runbook-capstone-') for n in nodes):
        raise SystemExit('Refusing installation: not the dedicated investigation cluster')
    uid = json.loads(command(['get', 'namespace', 'kube-system', '-o', 'json']))['metadata']['uid']
    for ns in ('copilot-system', 'dev-capstone', 'prod-capstone'):
        obj = resource('Namespace', ns)
        obj['metadata']['labels'] = {'runbook-copilot/agent': 'allowed' if ns == 'dev-capstone' else 'readonly'}
        apply(obj)
    for name in ('history-reader', 'dev-repair'):
        apply(resource('ServiceAccount', name, 'copilot-system'))
    rules = [
        {'apiGroups': [''], 'resources': ['pods', 'services', 'events'], 'verbs': ['get', 'list', 'watch']},
        {'apiGroups': ['apps'], 'resources': ['deployments', 'replicasets'], 'verbs': ['get', 'list', 'watch']},
        {'apiGroups': ['discovery.k8s.io'], 'resources': ['endpointslices'], 'verbs': ['get', 'list', 'watch']},
    ]
    apply(resource('ClusterRole', 'capstone-history-reader', rules=rules))
    apply(resource('ClusterRole', 'capstone-identity-reader', rules=[{
        'apiGroups': [''], 'resources': ['namespaces'], 'resourceNames': ['kube-system', 'dev-capstone', 'prod-capstone'], 'verbs': ['get']}]))
    for sa in ('history-reader', 'dev-repair'):
        apply(resource('ClusterRoleBinding', 'capstone-identity-' + sa,
                       roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': 'capstone-identity-reader'},
                       subjects=[{'kind': 'ServiceAccount', 'name': sa, 'namespace': 'copilot-system'}]))
    for ns in ('dev-capstone', 'prod-capstone'):
        subjects = [{'kind': 'ServiceAccount', 'name': 'history-reader', 'namespace': 'copilot-system'}]
        if ns == 'dev-capstone':
            subjects.append({'kind': 'ServiceAccount', 'name': 'dev-repair', 'namespace': 'copilot-system'})
        apply(resource('RoleBinding', 'history-reader', ns,
                       roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'ClusterRole', 'name': 'capstone-history-reader'}, subjects=subjects))
    apply(resource('Role', 'dev-selector-repair', 'dev-capstone', rules=[{
        'apiGroups': [''], 'resources': ['services'], 'resourceNames': ['demo-web'], 'verbs': ['patch']}]))
    apply(resource('RoleBinding', 'dev-selector-repair', 'dev-capstone',
                   roleRef={'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role', 'name': 'dev-selector-repair'},
                   subjects=[{'kind': 'ServiceAccount', 'name': 'dev-repair', 'namespace': 'copilot-system'}]))
    apply(resource('PersistentVolumeClaim', 'history', 'copilot-system', spec={
        'accessModes': ['ReadWriteOnce'], 'resources': {'requests': {'storage': '1Gi'}}}))
    apply(resource('Deployment', 'history', 'copilot-system', spec={
        'replicas': 1, 'strategy': {'type': 'Recreate'}, 'selector': {'matchLabels': {'app': 'history'}},
        'template': {'metadata': {'labels': {'app': 'history'}}, 'spec': {
            'serviceAccountName': 'history-reader',
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'fsGroup': 10001, 'seccompProfile': {'type': 'RuntimeDefault'}},
            'containers': [{'name': 'history', 'image': os.environ.get('HISTORY_IMAGE', 'runbook-history:capstone-v4'),
                            'imagePullPolicy': 'Never', 'ports': [{'containerPort': 8000}],
                            'env': [{'name': 'HISTORY_DB', 'value': '/history/history.sqlite'}, {'name': 'CLUSTER_UID', 'value': uid}],
                            'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                            'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '500m', 'memory': '384Mi'}},
                            'volumeMounts': [{'name': 'history', 'mountPath': '/history'}],
                            'readinessProbe': {'httpGet': {'path': '/health', 'port': 8000}, 'initialDelaySeconds': 5},
                            'livenessProbe': {'httpGet': {'path': '/health', 'port': 8000}, 'initialDelaySeconds': 20}}],
            'volumes': [{'name': 'history', 'persistentVolumeClaim': {'claimName': 'history'}}]}}}))
    apply(resource('Service', 'history', 'copilot-system', spec={'type': 'NodePort', 'selector': {'app': 'history'},
                  'ports': [{'port': 8000, 'targetPort': 8000, 'nodePort': 30811}]}))
    subprocess.run(K + ['-n', 'copilot-system', 'rollout', 'status', 'deployment/history', '--timeout=120s'], check=True)  # nosec B603: fixed rollout command
    # Refresh the short-lived, least-privilege interactive dev identity without printing its token.
    cfg = yaml.safe_load(KUBECONFIG.read_text())
    cfg = copy.deepcopy(cfg)
    token = command(['-n', 'copilot-system', 'create', 'token', 'dev-repair', '--duration=8h']).strip()
    cfg['users'] = [{'name': 'dev-repair', 'user': {'token': token}}]
    cfg['contexts'] = [{'name': 'kind-runbook-capstone-dev', 'context': {'cluster': cfg['clusters'][0]['name'], 'user': 'dev-repair', 'namespace': 'dev-capstone'}}]
    cfg['current-context'] = 'kind-runbook-capstone-dev'
    path = ROOT / '.agent/capstone-dev.kubeconfig'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        yaml.safe_dump(cfg, f)
    os.chmod(KUBECONFIG, 0o600)
    print('Cluster history installed; restricted dev access refreshed (8 hours). No default context used.')


if __name__ == '__main__':
    main()
