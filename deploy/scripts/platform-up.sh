#!/usr/bin/env bash
# Build ONE image, load it into a local kind cluster, deploy it to the `dev` namespace.
# `prod` is never touched here: use deploy/scripts/promote.sh to promote exactly what runs in dev.
#
#   bash deploy/scripts/platform-up.sh            (or: make platform-up)
#   LLM_API_KEY=sk-... bash deploy/scripts/platform-up.sh   # also creates the llm secret in dev and prod
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

CLUSTER="${CLUSTER:-runbook-lab}"
CTX="kind-${CLUSTER}"
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
TAG="${TAG:-$(date -u +%Y%m%d-%H%M%S)-${SHA}}"
IMAGE="${IMAGE:-runbook-copilot}"
CHART=deploy/helm/runbook-copilot

for t in docker kind kubectl helm; do command -v "$t" >/dev/null || { echo "missing tool: $t"; exit 1; }; done

kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER" --config labs/kind-config.yaml
k() { kubectl --context "$CTX" "$@"; }   # always pinned to the lab cluster, never your current context

echo ">> building ${IMAGE}:${TAG}"
docker build --build-arg APP_VERSION="$TAG" -t "${IMAGE}:${TAG}" .
kind load docker-image "${IMAGE}:${TAG}" --name "$CLUSTER"

echo ">> observability backend"
k apply -f deploy/k8s/observability.yaml

for ns in dev prod; do
  k create namespace "$ns" --dry-run=client -o yaml | k apply -f - >/dev/null
  if [ -n "${LLM_API_KEY:-}" ]; then
    k -n "$ns" create secret generic copilot-llm --from-literal=LLM_API_KEY="$LLM_API_KEY" \
      --dry-run=client -o yaml | k apply -f - >/dev/null
  fi
done
[ -n "${LLM_API_KEY:-}" ] || echo "!! LLM_API_KEY not set: dev starts without an LLM secret (retrieval-only mode)"

echo ">> deploying ${TAG} to dev"
helm --kube-context "$CTX" upgrade --install copilot "$CHART" -n dev -f "$CHART/values-dev.yaml" \
  --set image.repository="$IMAGE" --set image.tag="$TAG" --set image.pullPolicy=Never \
  $( [ -n "${LLM_API_KEY:-}" ] || echo "--set llm.existingSecret=" ) --wait --timeout 3m

cat <<MSG

dev is running ${IMAGE}:${TAG}
  kubectl --context ${CTX} -n dev port-forward svc/copilot-runbook-copilot 8000:80
  kubectl --context ${CTX} -n observability port-forward svc/lgtm 3000:3000      # Grafana (import observability/dashboards/copilot.json)
promote exactly this image:  make promote
MSG
