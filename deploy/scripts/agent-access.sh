#!/usr/bin/env bash
# Give the agent an identity for ONE namespace and write a kubeconfig for it.
#
#   bash deploy/scripts/agent-access.sh dev  lab-oomkilled     # reader + writer in that namespace, namespace labelled opt-in
#   bash deploy/scripts/agent-access.sh prod prod              # reader ONLY
#
# The kubeconfig (a short-lived token) is written to .agent/<env>.kubeconfig (gitignored, mode 600). Run as the cluster admin
# of the LAB cluster; it refuses any context that is not kind/k3d/minikube unless LAB_ALLOW_CONTEXT=1.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

ENVN="${1:?usage: agent-access.sh <dev|prod> <namespace>}"
NS="${2:?usage: agent-access.sh <dev|prod> <namespace>}"
[ "$ENVN" = dev ] || [ "$ENVN" = prod ] || { echo "env must be dev or prod"; exit 1; }
CLUSTER="${CLUSTER:-runbook-lab}"
CTX="${CTX:-kind-${CLUSTER}}"
case "$CTX" in
  kind-*|k3d-*|minikube*) ;;
  *) [ "${LAB_ALLOW_CONTEXT:-}" = "1" ] || { echo "refusing to run on context '$CTX' (not kind/k3d/minikube)"; exit 1; } ;;
esac
SA=$([ "$ENVN" = prod ] && echo copilot-agent-readonly || echo copilot-agent-dev)
k() { kubectl --context "$CTX" "$@"; }

k apply -f deploy/rbac/agent-rbac.yaml >/dev/null
k create namespace "$NS" --dry-run=client -o yaml | k apply -f - >/dev/null
k -n "$NS" create rolebinding copilot-agent-reader --clusterrole=copilot-agent-reader \
  --serviceaccount="copilot-agent:${SA}" --dry-run=client -o yaml | k apply -f - >/dev/null
if [ "$ENVN" = dev ]; then
  k -n "$NS" create rolebinding copilot-agent-writer --clusterrole=copilot-agent-writer \
    --serviceaccount="copilot-agent:${SA}" --dry-run=client -o yaml | k apply -f - >/dev/null
  k label namespace "$NS" runbook-copilot/agent=allowed --overwrite >/dev/null
fi

TOKEN="$(k -n copilot-agent create token "$SA" --duration=8h)"
SERVER="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.server}')"
CA="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
mkdir -p .agent
OUT=".agent/${ENVN}.kubeconfig"
( umask 077
cat > "$OUT" <<KCFG
apiVersion: v1
kind: Config
clusters:
  - name: ${CTX}
    cluster: { server: "${SERVER}", certificate-authority-data: "${CA}" }
users:
  - name: ${SA}
    user: { token: "${TOKEN}" }
contexts:
  - name: ${CTX}-agent-${ENVN}
    context: { cluster: ${CTX}, user: ${SA} }
current-context: ${CTX}-agent-${ENVN}
KCFG
)
echo "wrote ${OUT} (context ${CTX}-agent-${ENVN}, token valid 8h)"
echo "check:  kubectl --kubeconfig ${OUT} auth can-i patch deployments -n ${NS}   # dev: yes, prod: no"
echo "run:    python -m runbook_copilot.agent --env ${ENVN} -n ${NS} --kubeconfig ${OUT} --incident '...'"
